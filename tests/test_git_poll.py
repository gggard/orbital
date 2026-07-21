"""Git-poll auto-update fallback for redeploys (SPEC §4.2/FR-2.2)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orbital.config import Settings, get_settings
from orbital.gitutil import GitError
from orbital.models import App, AppState, AppType, Build, BuildPhase, PendingAction


def make_app(
    slug="demo",
    state=AppState.running,
    poll_enabled=True,
    poll_interval_seconds=None,
    last_polled_at=None,
    current_build_id=None,
) -> App:
    return App(
        id="abc123def456",
        slug=slug,
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=state,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
        poll_enabled=poll_enabled,
        poll_interval_seconds=poll_interval_seconds,
        last_polled_at=last_polled_at,
        current_build_id=current_build_id,
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _persist(app: App, build: Build | None = None) -> str:
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
        if build is not None:
            session.add(build)
    return app.id


def test_settings_reject_min_interval_above_default_interval():
    with pytest.raises(ValueError, match="ORBITAL_GIT_POLL_MIN_INTERVAL_SECONDS"):
        Settings(
            git_poll_default_interval_seconds=300,
            git_poll_min_interval_seconds=600,
            _env_file=None,
        )


def test_poll_disabled_by_default_is_noop(reconciler):
    from orbital import db as db_mod

    app_id = _persist(make_app(poll_enabled=False))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("orbital.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        mock_resolve.assert_not_called()
        assert app.pending_action == PendingAction.none
        assert app.last_polled_at is None


def test_poll_skips_when_interval_not_elapsed(reconciler):
    from orbital import db as db_mod

    app_id = _persist(make_app(last_polled_at=datetime.now(UTC) - timedelta(seconds=30)))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("orbital.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        mock_resolve.assert_not_called()


def test_poll_triggers_redeploy_on_new_commit(reconciler):
    from orbital import db as db_mod

    build = Build(
        id="bld000000001",
        app_id="abc123def456",
        commit_sha="aaa111",
        phase=BuildPhase.succeeded,
    )
    app_id = _persist(make_app(current_build_id="bld000000001"), build=build)
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch(
            "orbital.k8s.reconciler.resolve_branch_head", return_value="bbb222"
        ):
            reconciler._maybe_poll_git(session, app)
        assert app.pending_action == PendingAction.deploy
        assert app.last_polled_at is not None


def test_poll_noop_when_commit_unchanged(reconciler):
    from orbital import db as db_mod

    build = Build(
        id="bld000000001",
        app_id="abc123def456",
        commit_sha="aaa111",
        phase=BuildPhase.succeeded,
    )
    app_id = _persist(make_app(current_build_id="bld000000001"), build=build)
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch(
            "orbital.k8s.reconciler.resolve_branch_head", return_value="aaa111"
        ):
            reconciler._maybe_poll_git(session, app)
        assert app.pending_action == PendingAction.none


def test_poll_handles_git_error_without_crashing(reconciler):
    from orbital import db as db_mod

    build = Build(
        id="bld000000001",
        app_id="abc123def456",
        commit_sha="aaa111",
        phase=BuildPhase.succeeded,
    )
    app_id = _persist(make_app(current_build_id="bld000000001"), build=build)
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch(
            "orbital.k8s.reconciler.resolve_branch_head",
            side_effect=GitError("host unreachable"),
        ):
            reconciler._maybe_poll_git(session, app)  # must not raise
        assert app.pending_action == PendingAction.none
        # bookkeeping still advances so a persistently-broken host doesn't
        # get hammered every tick
        assert app.last_polled_at is not None


def test_poll_respects_per_app_interval_override(reconciler):
    from orbital import db as db_mod

    app_id = _persist(
        make_app(
            poll_interval_seconds=3600,
            last_polled_at=datetime.now(UTC) - timedelta(minutes=15),
        )
    )
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("orbital.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        # 15 min < the 1h per-app override, even though it's past the 10 min
        # platform default
        mock_resolve.assert_not_called()


def test_poll_clamps_per_app_interval_to_platform_minimum(monkeypatch, tmp_path):
    """A per-app interval below the platform minimum (e.g. set before the
    minimum existed, or written directly to the DB) must not let an app
    poll more often than the floor."""
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_GIT_POLL_MIN_INTERVAL_SECONDS", "600")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    reconciler = Reconciler()
    # per-app override (1s) is far below the 10 min platform minimum
    app_id = _persist(
        make_app(
            poll_interval_seconds=1,
            last_polled_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("orbital.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        # 5 min elapsed < the 10 min platform minimum, so no poll yet
        mock_resolve.assert_not_called()
    get_settings.cache_clear()


# -- API: poll fields on create/patch ---------------------------------------


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


def make_client_app(client, slug="demo", **extra):
    return client.post(
        "/api/v1/apps",
        json={"slug": slug, "repo_url": "https://github.com/x/y", "branch": "main", **extra},
    )


def test_create_app_poll_defaults(client):
    body = make_client_app(client).json()
    assert body["poll_enabled"] is False
    assert body["poll_interval_seconds"] is None
    assert body["last_polled_at"] is None


def test_create_app_can_enable_polling(client):
    body = make_client_app(client, poll_enabled=True, poll_interval_seconds=1800).json()
    assert body["poll_enabled"] is True
    assert body["poll_interval_seconds"] == 1800


def test_patch_poll_settings(client):
    app_id = make_client_app(client).json()["id"]
    r = client.patch(
        f"/api/v1/apps/{app_id}",
        json={"poll_enabled": True, "poll_interval_seconds": 900},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["poll_enabled"] is True
    assert body["poll_interval_seconds"] == 900


def test_patch_poll_interval_must_be_positive(client):
    app_id = make_client_app(client).json()["id"]
    r = client.patch(f"/api/v1/apps/{app_id}", json={"poll_interval_seconds": 0})
    assert r.status_code == 422


def test_patch_poll_interval_rejects_below_platform_minimum(client):
    app_id = make_client_app(client).json()["id"]
    under_min = get_settings().git_poll_min_interval_seconds - 1
    r = client.patch(f"/api/v1/apps/{app_id}", json={"poll_interval_seconds": under_min})
    assert r.status_code == 422
    assert "platform minimum" in r.text


def test_create_app_rejects_poll_interval_below_platform_minimum(client):
    under_min = get_settings().git_poll_min_interval_seconds - 1
    r = make_client_app(client, poll_enabled=True, poll_interval_seconds=under_min)
    assert r.status_code == 422
    assert "platform minimum" in r.text


def test_me_reports_poll_defaults_and_minimum(client):
    body = client.get("/api/v1/me").json()
    s = get_settings()
    assert body["git_poll_default_interval_seconds"] == s.git_poll_default_interval_seconds
    assert body["git_poll_min_interval_seconds"] == s.git_poll_min_interval_seconds
