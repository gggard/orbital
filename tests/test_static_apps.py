"""Static-site apps: a second app_type alongside streamlit, sharing the same
build -> image -> Deployment/Service/Ingress -> reconciler -> hibernation
pipeline (see SPEC and docs/API.md).
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from orbital.config import get_settings
from orbital.models import App, AppType, PendingAction


def make_app(app_id="abc123def456", slug="demo", app_type=AppType.static) -> App:
    return App(
        id=app_id,
        slug=slug,
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=app_type,
        output_dir=".",
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
        current_image="registry.test/apps/abc123def456:bld1",
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_ROUTING_MODE", "path")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s import client as k8s_client
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    for name in ("batch", "apps_v1", "core", "networking"):
        monkeypatch.setattr(k8s_client, name, MagicMock())
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _persist(app: App) -> str:
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
    return app.id


def test_ensure_base_path_noop_for_static_apps_in_path_mode(reconciler):
    """Regression: static apps have no STREAMLIT_SERVER_BASE_URL_PATH env
    var, so without an app_type guard, _ensure_base_path would see a
    permanent "" != desired_path mismatch and redeploy on every tick.
    """
    from orbital import db as db_mod
    from orbital.k8s import client as k8s_client

    app_id = _persist(make_app(app_type=AppType.static))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._ensure_base_path(app)
        k8s_client.apps_v1().read_namespaced_deployment.assert_not_called()


def test_ensure_base_path_still_converges_streamlit_apps(reconciler):
    from orbital import db as db_mod
    from orbital.k8s import client as k8s_client

    app_id = _persist(make_app(app_type=AppType.streamlit))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._ensure_base_path(app)
        k8s_client.apps_v1().read_namespaced_deployment.assert_called_once()


# -- API: creating/updating static apps --------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_create_static_app_without_main_file_or_python_version(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "static-demo",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["app_type"] == "static"
    assert body["main_file"] is None
    assert body["python_version"] is None
    assert body["output_dir"] == "."


def test_create_static_app_with_build_command(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "static-build",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "build_command": "npm run build",
            "output_dir": "dist",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["build_command"] == "npm run build"
    assert body["output_dir"] == "dist"


def test_create_static_app_rejects_main_file(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "bad",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "main_file": "app.py",
        },
    )
    assert r.status_code == 422


def test_create_static_app_rejects_python_version(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "bad",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "python_version": "3.12",
        },
    )
    assert r.status_code == 422


def test_create_static_app_rejects_secrets(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "bad",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "secrets_toml": "a = 1",
        },
    )
    assert r.status_code == 422


def test_create_streamlit_app_rejects_build_command(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "bad",
            "repo_url": "https://github.com/x/y",
            "build_command": "npm run build",
        },
    )
    assert r.status_code == 422


def test_create_streamlit_app_defaults_main_file(client):
    r = client.post(
        "/api/v1/apps", json={"slug": "sl-demo", "repo_url": "https://github.com/x/y"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["app_type"] == "streamlit"
    assert body["main_file"] == "streamlit_app.py"
    assert body["python_version"] == "3.12"


def test_patch_static_app_rejects_python_version(client):
    app_id = client.post(
        "/api/v1/apps",
        json={"slug": "static-demo", "repo_url": "https://github.com/x/y", "app_type": "static"},
    ).json()["id"]
    r = client.patch(f"/api/v1/apps/{app_id}", json={"python_version": "3.12"})
    assert r.status_code == 422


def test_patch_static_app_build_command_triggers_rebuild(client):
    app_id = client.post(
        "/api/v1/apps",
        json={"slug": "static-demo", "repo_url": "https://github.com/x/y", "app_type": "static"},
    ).json()["id"]
    r = client.patch(f"/api/v1/apps/{app_id}", json={"build_command": "npm run build"})
    assert r.status_code == 200, r.text
    assert r.json()["build_command"] == "npm run build"


def test_patch_streamlit_app_rejects_build_command(client):
    app_id = client.post(
        "/api/v1/apps", json={"slug": "sl-demo", "repo_url": "https://github.com/x/y"}
    ).json()["id"]
    r = client.patch(f"/api/v1/apps/{app_id}", json={"build_command": "npm run build"})
    assert r.status_code == 422
