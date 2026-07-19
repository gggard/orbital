"""Hibernation: idle apps sleep, wake on the next request (SPEC §4.8/§5.6)."""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from kubernetes.client import ApiException

from orbital.config import Settings, get_settings
from orbital.k8s import resources
from orbital.models import App, AppState


def make_app(
    slug="demo",
    public=True,
    state=AppState.running,
    hibernate_enabled=True,
    hibernate_after_seconds=None,
) -> App:
    return App(
        id="abc123def456",
        slug=slug,
        repo_url="https://github.com/x/y",
        public=public,
        state=state,
        owner_groups=[],
        allowed_groups=[],
        hibernate_enabled=hibernate_enabled,
        hibernate_after_seconds=hibernate_after_seconds,
    )


# -- k8s/resources.ingress(): backend + activity-beacon annotations --------


@pytest.fixture
def settings() -> Settings:
    return Settings(
        apps_domain="apps.example.com",
        control_plane_service_host="cp.orbital-platform.svc.cluster.local",
        _env_file=None,
    )


def _backend(ing: dict) -> dict:
    return ing["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]


def test_sleeping_app_routes_to_wake_service(settings):
    ing = resources.ingress(make_app(state=AppState.sleeping), settings)
    backend = _backend(ing)
    assert backend["name"] == resources.WAKE_SERVICE_NAME
    assert backend["port"]["number"] == settings.control_plane_service_port


def test_running_app_routes_to_own_service(settings):
    app = make_app(state=AppState.running)
    ing = resources.ingress(app, settings)
    assert _backend(ing)["name"] == resources.name_for(app)


def test_public_app_gets_activity_beacon(settings):
    app = make_app(public=True, state=AppState.running)
    ann = resources.ingress(app, settings)["metadata"]["annotations"]
    assert ann["nginx.ingress.kubernetes.io/auth-url"] == (
        f"{settings.internal_base_url()}/activity/{app.id}"
    )
    assert "nginx.ingress.kubernetes.io/auth-signin" not in ann


def test_public_app_activity_beacon_uses_authz_base_url_override():
    # dev setups where the control plane isn't an in-cluster Service (see
    # ORBITAL_AUTHZ_BASE_URL in docs/DEVELOPMENT.md) need this for public apps
    # too - not just the private-app /authz annotation.
    s = Settings(
        apps_domain="apps.example.com",
        control_plane_service_host="cp.orbital-platform.svc.cluster.local",
        authz_base_url="http://192.168.58.1:8000",
        _env_file=None,
    )
    app = make_app(public=True, state=AppState.running)
    ann = resources.ingress(app, s)["metadata"]["annotations"]
    assert ann["nginx.ingress.kubernetes.io/auth-url"] == (
        f"http://192.168.58.1:8000/activity/{app.id}"
    )


def test_sleeping_app_has_no_activity_beacon(settings):
    app = make_app(public=True, state=AppState.sleeping)
    ann = resources.ingress(app, settings)["metadata"]["annotations"]
    assert "nginx.ingress.kubernetes.io/auth-url" not in ann


def test_per_app_hibernation_disabled_skips_beacon(settings):
    app = make_app(public=True, state=AppState.running, hibernate_enabled=False)
    ann = resources.ingress(app, settings)["metadata"]["annotations"]
    assert "nginx.ingress.kubernetes.io/auth-url" not in ann


def test_settings_reject_max_timeout_below_default_timeout():
    with pytest.raises(ValueError, match="ORBITAL_HIBERNATION_MAX_TIMEOUT_SECONDS"):
        Settings(
            hibernation_timeout_seconds=7200,
            hibernation_max_timeout_seconds=3600,
            _env_file=None,
        )


def test_platform_hibernation_disabled_skips_wake_backend():
    s = Settings(apps_domain="apps.example.com", control_plane_service_host="", _env_file=None)
    app = make_app(state=AppState.sleeping)
    assert _backend(resources.ingress(app, s))["name"] == resources.name_for(app)


def test_private_app_auth_url_falls_back_to_internal_base_url():
    s = Settings(
        apps_domain="apps.example.com",
        auth_enabled=True,
        control_plane_service_host="cp.orbital-platform.svc.cluster.local",
        _env_file=None,
    )
    app = make_app(public=False, state=AppState.running)
    ing = resources.ingress(app, s)
    assert ing["metadata"]["annotations"]["nginx.ingress.kubernetes.io/auth-url"] == (
        f"{s.internal_base_url()}/authz/{app.id}"
    )


def test_wake_service_shape(settings):
    svc = resources.wake_service(settings)
    assert svc["metadata"]["name"] == resources.WAKE_SERVICE_NAME
    assert svc["spec"]["type"] == "ExternalName"
    assert svc["spec"]["externalName"] == settings.control_plane_service_host


# -- reconciler: hibernate / wake state transitions -------------------------


@pytest.fixture
def reconciler(monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", "sqlite://")
    get_settings.cache_clear()
    from orbital.k8s.reconciler import Reconciler

    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _mock_k8s(monkeypatch):
    from orbital.k8s import client as k8s_client

    apps_v1, core, networking = MagicMock(), MagicMock(), MagicMock()
    networking.read_namespaced_ingress.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)
    monkeypatch.setattr(k8s_client, "networking", lambda: networking)
    return apps_v1, core, networking


def test_maybe_hibernate_scales_to_zero_after_timeout(reconciler, monkeypatch):
    apps_v1, _, networking = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.running)
    app.last_active_at = datetime.now(UTC) - timedelta(hours=13)
    reconciler._maybe_hibernate(app)
    assert app.state == AppState.sleeping
    call = apps_v1.patch_namespaced_deployment.call_args
    assert call.args[2]["spec"]["replicas"] == 0
    networking.create_namespaced_ingress.assert_called_once()


def test_maybe_hibernate_skips_when_not_idle(reconciler, monkeypatch):
    apps_v1, _, _networking = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.running)
    app.last_active_at = datetime.now(UTC)
    reconciler._maybe_hibernate(app)
    assert app.state == AppState.running
    apps_v1.patch_namespaced_deployment.assert_not_called()


def test_maybe_hibernate_respects_disabled_flag(reconciler, monkeypatch):
    apps_v1, _, _n = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.running, hibernate_enabled=False)
    app.last_active_at = datetime.now(UTC) - timedelta(hours=13)
    reconciler._maybe_hibernate(app)
    assert app.state == AppState.running
    apps_v1.patch_namespaced_deployment.assert_not_called()


def test_maybe_hibernate_respects_per_app_override(reconciler, monkeypatch):
    apps_v1, _, _n = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.running, hibernate_after_seconds=3600)
    app.last_active_at = datetime.now(UTC) - timedelta(minutes=90)
    reconciler._maybe_hibernate(app)
    assert app.state == AppState.sleeping


def test_maybe_hibernate_clamps_per_app_override_to_platform_maximum(monkeypatch):
    """A per-app timeout beyond the platform maximum (e.g. set before the
    maximum existed, or written directly to the DB) must not let an app
    stay awake past it."""
    monkeypatch.setenv("ORBITAL_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ORBITAL_HIBERNATION_TIMEOUT_SECONDS", "1800")
    monkeypatch.setenv("ORBITAL_HIBERNATION_MAX_TIMEOUT_SECONDS", "3600")
    get_settings.cache_clear()
    from orbital.k8s.reconciler import Reconciler

    _mock_k8s(monkeypatch)
    reconciler = Reconciler()
    # per-app override (24h) far exceeds the 1h platform maximum
    app = make_app(state=AppState.running, hibernate_after_seconds=24 * 3600)
    app.last_active_at = datetime.now(UTC) - timedelta(hours=2)
    reconciler._maybe_hibernate(app)
    assert app.state == AppState.sleeping
    get_settings.cache_clear()


def test_maybe_hibernate_survives_naive_last_active_at_after_db_roundtrip(tmp_path, monkeypatch):
    """Regression: sqlite drops the UTC offset on a DateTime(timezone=True)
    round-trip, so an app fetched fresh from the DB (as the reconciler does
    every tick, not the in-memory objects the other tests above use) can
    have a naive last_active_at. _maybe_hibernate must not crash comparing
    it against an aware `datetime.now(UTC)`.
    """
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    _mock_k8s(monkeypatch)

    from orbital import db as db_mod
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    reconciler = Reconciler()

    with db_mod.session_scope() as session:
        app = make_app(state=AppState.running)
        app.last_active_at = datetime.now(UTC) - timedelta(hours=13)
        session.add(app)

    with db_mod.session_scope() as session:
        reloaded = session.get(App, "abc123def456")
        assert reloaded.last_active_at.tzinfo is None  # confirms the round-trip stripped it

        reconciler._maybe_hibernate(reloaded)  # must not raise
        assert reloaded.state == AppState.sleeping

    get_settings.cache_clear()


def test_maybe_wake_scales_to_one_on_request(reconciler, monkeypatch):
    apps_v1, _, _n = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.sleeping)
    app.wake_requested_at = datetime.now(UTC)
    reconciler._maybe_wake(app)
    assert app.state == AppState.deploying
    assert app.wake_requested_at is None
    call = apps_v1.patch_namespaced_deployment.call_args
    assert call.args[2]["spec"]["replicas"] == 1


def test_maybe_wake_noop_without_request(reconciler, monkeypatch):
    apps_v1, _, _n = _mock_k8s(monkeypatch)
    app = make_app(state=AppState.sleeping)
    reconciler._maybe_wake(app)
    assert app.state == AppState.sleeping
    apps_v1.patch_namespaced_deployment.assert_not_called()


# -- API: hibernation fields, wake endpoint, activity beacon ---------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_APPS_DOMAIN", "apps.local")  # .env may set something else
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def make_client_app(client, slug="demo", **extra):
    return client.post(
        "/api/v1/apps",
        json={"slug": slug, "repo_url": "https://github.com/x/y", "branch": "main", **extra},
    )


def test_create_app_hibernation_defaults(client):
    body = make_client_app(client).json()
    assert body["hibernate_enabled"] is True
    assert body["hibernate_after_seconds"] is None
    assert "last_active_at" in body


def test_create_app_can_disable_hibernation(client):
    body = make_client_app(client, hibernate_enabled=False).json()
    assert body["hibernate_enabled"] is False


def test_patch_hibernation_settings(client):
    app_id = make_client_app(client).json()["id"]
    r = client.patch(
        f"/api/v1/apps/{app_id}",
        json={"hibernate_enabled": False, "hibernate_after_seconds": 3600},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hibernate_enabled"] is False
    assert body["hibernate_after_seconds"] == 3600


def test_patch_hibernate_after_seconds_must_be_positive(client):
    app_id = make_client_app(client).json()["id"]
    r = client.patch(f"/api/v1/apps/{app_id}", json={"hibernate_after_seconds": 0})
    assert r.status_code == 422


def test_patch_hibernate_after_seconds_rejects_above_platform_maximum(client):
    app_id = make_client_app(client).json()["id"]
    over_max = get_settings().hibernation_max_timeout_seconds + 1
    r = client.patch(f"/api/v1/apps/{app_id}", json={"hibernate_after_seconds": over_max})
    assert r.status_code == 422
    assert "platform maximum" in r.text


def test_create_app_rejects_hibernate_after_seconds_above_platform_maximum(client):
    over_max = get_settings().hibernation_max_timeout_seconds + 1
    r = make_client_app(client, hibernate_after_seconds=over_max)
    assert r.status_code == 422
    assert "platform maximum" in r.text


def test_me_reports_hibernation_defaults_and_maximum(client):
    body = client.get("/api/v1/me").json()
    s = get_settings()
    assert body["hibernation_timeout_seconds"] == s.hibernation_timeout_seconds
    assert body["hibernation_max_timeout_seconds"] == s.hibernation_max_timeout_seconds


def test_wake_requires_sleeping_state(client):
    app_id = make_client_app(client).json()["id"]
    r = client.post(f"/api/v1/apps/{app_id}/wake")
    assert r.status_code == 409


def test_activity_ping_touches_last_active_at(client):
    app_id = make_client_app(client).json()["id"]
    before = client.get(f"/api/v1/apps/{app_id}").json()["last_active_at"]
    time.sleep(0.01)
    assert client.get(f"/activity/{app_id}").status_code == 200
    after = client.get(f"/api/v1/apps/{app_id}").json()["last_active_at"]
    assert after > before


def test_activity_ping_unknown_app_still_200(client):
    assert client.get("/activity/nope").status_code == 200


# -- wake interstitial middleware (Host-header based) -----------------------


def _sleep_app(client, slug="sleepy"):
    app_id = make_client_app(client, slug=slug).json()["id"]
    from sqlalchemy import select

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.scalar(select(App).where(App.id == app_id))
        app.state = AppState.sleeping
    return app_id


def test_sleeping_app_host_shows_interstitial(client):
    app_id = _sleep_app(client)
    r = client.get("/", headers={"Host": "sleepy.apps.local"})
    assert r.status_code == 200
    assert "Waking up" in r.text
    assert client.get(f"/api/v1/apps/{app_id}").json()["state"] == "sleeping"
    # a wake request was recorded
    from sqlalchemy import select

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.scalar(select(App).where(App.id == app_id))
        assert app.wake_requested_at is not None


def test_unrelated_host_is_not_intercepted(client):
    r = client.get("/healthz", headers={"Host": "streamlit.local"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_unknown_slug_subdomain_falls_through(client):
    r = client.get("/", headers={"Host": "nosuchapp.apps.local"})
    # falls through to the normal "/" route (the dev dashboard), not the
    # wake interstitial
    assert "Waking up" not in r.text
