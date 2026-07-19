"""Git-poll auto-update fallback for redeploys (SPEC §4.2/FR-2.2)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from streamlit_host.config import get_settings
from streamlit_host.gitutil import GitError
from streamlit_host.models import App, AppState, Build, BuildPhase, PendingAction


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
    monkeypatch.setenv("SH_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from streamlit_host import db as db_mod
    from streamlit_host.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _persist(app: App, build: Build | None = None) -> str:
    from streamlit_host import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
        if build is not None:
            session.add(build)
    return app.id


def test_poll_disabled_by_default_is_noop(reconciler):
    from streamlit_host import db as db_mod

    app_id = _persist(make_app(poll_enabled=False))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("streamlit_host.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        mock_resolve.assert_not_called()
        assert app.pending_action == PendingAction.none
        assert app.last_polled_at is None


def test_poll_skips_when_interval_not_elapsed(reconciler):
    from streamlit_host import db as db_mod

    app_id = _persist(make_app(last_polled_at=datetime.now(UTC) - timedelta(seconds=30)))
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("streamlit_host.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        mock_resolve.assert_not_called()


def test_poll_triggers_redeploy_on_new_commit(reconciler):
    from streamlit_host import db as db_mod

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
            "streamlit_host.k8s.reconciler.resolve_branch_head", return_value="bbb222"
        ):
            reconciler._maybe_poll_git(session, app)
        assert app.pending_action == PendingAction.deploy
        assert app.last_polled_at is not None


def test_poll_noop_when_commit_unchanged(reconciler):
    from streamlit_host import db as db_mod

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
            "streamlit_host.k8s.reconciler.resolve_branch_head", return_value="aaa111"
        ):
            reconciler._maybe_poll_git(session, app)
        assert app.pending_action == PendingAction.none


def test_poll_handles_git_error_without_crashing(reconciler):
    from streamlit_host import db as db_mod

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
            "streamlit_host.k8s.reconciler.resolve_branch_head",
            side_effect=GitError("host unreachable"),
        ):
            reconciler._maybe_poll_git(session, app)  # must not raise
        assert app.pending_action == PendingAction.none
        # bookkeeping still advances so a persistently-broken host doesn't
        # get hammered every tick
        assert app.last_polled_at is not None


def test_poll_respects_per_app_interval_override(reconciler):
    from streamlit_host import db as db_mod

    app_id = _persist(
        make_app(
            poll_interval_seconds=3600,
            last_polled_at=datetime.now(UTC) - timedelta(minutes=15),
        )
    )
    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        with patch("streamlit_host.k8s.reconciler.resolve_branch_head") as mock_resolve:
            reconciler._maybe_poll_git(session, app)
        # 15 min < the 1h per-app override, even though it's past the 10 min
        # platform default
        mock_resolve.assert_not_called()


# -- API: poll fields on create/patch ---------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SH_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("SH_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("SH_UI_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    from streamlit_host import db
    from streamlit_host.main import app

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
