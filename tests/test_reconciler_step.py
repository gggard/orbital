"""Reconciler.step(): the per-tick dispatcher that routes an app to the
right handler based on pending_action/state. The handlers themselves
(_check_rollout, _maybe_hibernate, _maybe_wake, ...) each have their own
focused tests elsewhere; here we only verify step() calls the right ones
with the right arguments and in the right combinations.
"""

from unittest.mock import MagicMock

import pytest

from orbital.config import get_settings
from orbital.models import App, AppState, AppType, PendingAction


def make_app(state=AppState.running, pending_action=PendingAction.none, **extra) -> App:
    return App(
        id="abc123def456",
        slug="demo",
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=state,
        pending_action=pending_action,
        owner_groups=[],
        allowed_groups=[],
        **extra,
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    r = Reconciler()
    for method in (
        "_delete_app",
        "_start_build",
        "_check_build",
        "_check_rollout",
        "_ensure_ingress",
        "_ensure_base_path",
        "_maybe_hibernate",
        "_maybe_wake",
        "_restart",
        "_deploy",
        "_maybe_poll_git",
        "_maybe_scan",
    ):
        monkeypatch.setattr(r, method, MagicMock())
    yield r
    get_settings.cache_clear()


def _step(reconciler, app):
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        reconciler.step(session, app)
        return session


def test_pending_delete_short_circuits_everything_else(reconciler):
    app = make_app(state=AppState.running, pending_action=PendingAction.delete)
    _step(reconciler, app)
    reconciler._delete_app.assert_called_once()
    reconciler._start_build.assert_not_called()
    reconciler._check_rollout.assert_not_called()
    reconciler._maybe_hibernate.assert_not_called()


def test_pending_deploy_starts_build_unless_already_building(reconciler):
    app = make_app(state=AppState.created, pending_action=PendingAction.deploy)
    _step(reconciler, app)
    reconciler._start_build.assert_called_once()
    reconciler._check_build.assert_not_called()


def test_pending_deploy_while_building_checks_build_instead(reconciler):
    app = make_app(state=AppState.building, pending_action=PendingAction.deploy)
    _step(reconciler, app)
    reconciler._start_build.assert_not_called()
    reconciler._check_build.assert_called_once()


def test_building_state_only_checks_build(reconciler):
    app = make_app(state=AppState.building)
    _step(reconciler, app)
    reconciler._check_build.assert_called_once()
    reconciler._check_rollout.assert_not_called()
    reconciler._maybe_poll_git.assert_not_called()


def test_deploying_state_checks_rollout(reconciler):
    app = make_app(state=AppState.deploying)
    _step(reconciler, app)
    reconciler._check_rollout.assert_called_once()
    reconciler._maybe_hibernate.assert_not_called()
    reconciler._maybe_wake.assert_not_called()


def test_running_state_ensures_ingress_and_maybe_hibernates(reconciler):
    app = make_app(state=AppState.running)
    _step(reconciler, app)
    reconciler._ensure_ingress.assert_called_once()
    reconciler._ensure_base_path.assert_called_once()
    reconciler._maybe_hibernate.assert_called_once()
    reconciler._maybe_wake.assert_not_called()


def test_sleeping_state_ensures_ingress_and_maybe_wakes(reconciler):
    app = make_app(state=AppState.sleeping)
    _step(reconciler, app)
    reconciler._ensure_ingress.assert_called_once()
    reconciler._maybe_wake.assert_called_once()
    reconciler._maybe_hibernate.assert_not_called()


def test_reboot_pending_on_running_app_restarts_and_moves_to_deploying(reconciler):
    app = make_app(state=AppState.running, pending_action=PendingAction.reboot)
    _step(reconciler, app)
    reconciler._restart.assert_called_once()
    assert app.pending_action == PendingAction.none
    assert app.state == AppState.deploying


def test_dirty_secrets_on_running_app_redeploys(reconciler):
    app = make_app(state=AppState.running, secrets_dirty=True, current_image="img:1")
    _step(reconciler, app)
    reconciler._deploy.assert_called_once()
    assert app.secrets_dirty is False
    assert app.state == AppState.deploying


def test_dirty_secrets_without_current_image_is_a_noop(reconciler):
    app = make_app(state=AppState.running, secrets_dirty=True, current_image=None)
    _step(reconciler, app)
    reconciler._deploy.assert_not_called()
    assert app.state == AppState.running


def test_idle_running_app_polls_git_and_scans(reconciler):
    app = make_app(state=AppState.running)
    _step(reconciler, app)
    reconciler._maybe_poll_git.assert_called_once()
    reconciler._maybe_scan.assert_called_once()


def test_building_app_never_polls_git_or_scans(reconciler):
    app = make_app(state=AppState.building)
    _step(reconciler, app)
    reconciler._maybe_poll_git.assert_not_called()
    reconciler._maybe_scan.assert_not_called()


def test_pending_action_blocks_poll_git_and_scan(reconciler):
    app = make_app(state=AppState.running, pending_action=PendingAction.reboot)
    _step(reconciler, app)
    reconciler._maybe_poll_git.assert_not_called()
    reconciler._maybe_scan.assert_not_called()
