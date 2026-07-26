"""_check_rollout: surfacing crash loops / image-pull errors instead of
waiting forever for a Deployment that will never become ready (see the
comment above the pod scan in reconciler.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbital.config import get_settings
from orbital.models import App, AppState, AppType, PendingAction


def make_app() -> App:
    return App(
        id="abc123def456",
        slug="demo",
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=AppState.deploying,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
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


def _deployment(ready_replicas=0, updated_replicas=0):
    status = SimpleNamespace(ready_replicas=ready_replicas, updated_replicas=updated_replicas)
    return SimpleNamespace(status=status)


def _pod(waiting_reason=None, waiting_message=None):
    waiting = None
    if waiting_reason:
        waiting = SimpleNamespace(reason=waiting_reason, message=waiting_message)
    container_status = SimpleNamespace(state=SimpleNamespace(waiting=waiting))
    return SimpleNamespace(status=SimpleNamespace(container_statuses=[container_status]))


def test_check_rollout_marks_running_once_ready(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client

    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment.return_value = _deployment(
        ready_replicas=1, updated_replicas=1
    )
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)

    app = make_app()
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        reconciler._check_rollout(session, app)

    assert app.state == AppState.running
    assert app.error is None


def test_check_rollout_surfaces_crash_loop_backoff(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client

    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment.return_value = _deployment()
    core = MagicMock()
    core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[_pod("CrashLoopBackOff", "back-off restarting failed container")]
    )
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)

    app = make_app()
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        reconciler._check_rollout(session, app)

    assert app.state == AppState.deploy_failed
    assert app.error == "CrashLoopBackOff: back-off restarting failed container"


def test_check_rollout_no_deployment_yet_is_a_noop(reconciler, monkeypatch):
    from kubernetes.client import ApiException

    from orbital.k8s import client as k8s_client

    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)

    app = make_app()
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        reconciler._check_rollout(session, app)

    assert app.state == AppState.deploying
