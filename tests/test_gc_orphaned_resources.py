"""Regression tests for #23: apps_namespace Deployment/Service/Ingress/Secret
objects whose app-id label has no matching row in the DB (leftovers from DB/
cluster drift) are never cleaned up, and can permanently block a new app from
claiming a previously-used slug/host.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbital.config import get_settings
from orbital.models import App, AppType, PendingAction


def make_app(app_id="abc123def456", slug="demo") -> App:
    return App(
        id=app_id,
        slug=slug,
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
    )


def _item(name: str, app_id: str | None):
    labels = {"app.orbital.io/app-id": app_id} if app_id else {}
    return SimpleNamespace(metadata=SimpleNamespace(name=name, labels=labels))


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    r = Reconciler()
    monkeypatch.setattr(r, "step", MagicMock(return_value=None))
    yield r
    get_settings.cache_clear()


def _mock_k8s(monkeypatch, *, deployments=(), services=(), ingresses=(), secrets=()):
    from orbital.k8s import client as k8s_client

    batch, apps_v1, core, networking = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    apps_v1.list_namespaced_deployment.return_value = SimpleNamespace(items=list(deployments))
    core.list_namespaced_service.return_value = SimpleNamespace(items=list(services))
    core.list_namespaced_secret.return_value = SimpleNamespace(items=list(secrets))
    networking.list_namespaced_ingress.return_value = SimpleNamespace(items=list(ingresses))
    core.list_namespaced_pod.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(k8s_client, "batch", lambda: batch)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)
    monkeypatch.setattr(k8s_client, "networking", lambda: networking)
    return batch, apps_v1, core, networking


def _persist(app: App) -> str:
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
    return app.id


def test_gc_deletes_orphaned_resources_but_spares_live_app(reconciler, monkeypatch):
    _persist(make_app())
    _batch, apps_v1, core, networking = _mock_k8s(
        monkeypatch,
        deployments=[_item("app-abc123def456", "abc123def456"), _item("app-orphan0001", "orphan0001")],
        services=[_item("app-abc123def456", "abc123def456"), _item("app-orphan0001", "orphan0001")],
        ingresses=[_item("app-abc123def456", "abc123def456"), _item("app-orphan0001", "orphan0001")],
        secrets=[_item("app-orphan0001-secrets", "orphan0001")],
    )

    reconciler.tick()

    apps_v1.delete_namespaced_deployment.assert_called_once_with(
        "app-orphan0001", reconciler.settings.apps_namespace
    )
    core.delete_namespaced_service.assert_called_once_with(
        "app-orphan0001", reconciler.settings.apps_namespace
    )
    networking.delete_namespaced_ingress.assert_called_once_with(
        "app-orphan0001", reconciler.settings.apps_namespace
    )
    core.delete_namespaced_secret.assert_called_once_with(
        "app-orphan0001-secrets", reconciler.settings.apps_namespace
    )


def test_gc_skips_resources_with_no_app_id_label(reconciler, monkeypatch):
    """Non-app-scoped resources (e.g. the hibernation wake-proxy Service)
    aren't returned by the app-id label selector in the first place, but
    guard the label-missing case defensively too."""
    _persist(make_app())
    _batch, apps_v1, core, networking = _mock_k8s(
        monkeypatch, services=[_item("sh-wake-proxy", None)]
    )

    reconciler.tick()

    core.delete_namespaced_service.assert_not_called()


def test_gc_runs_once_then_waits_for_the_interval(reconciler, monkeypatch):
    _persist(make_app())
    _batch, apps_v1, _core, _networking = _mock_k8s(monkeypatch)

    reconciler.tick()
    assert apps_v1.list_namespaced_deployment.call_count == 1

    reconciler.tick()
    reconciler.tick()
    assert apps_v1.list_namespaced_deployment.call_count == 1, (
        "gc should not re-list every tick within _GC_INTERVAL_SECONDS"
    )
