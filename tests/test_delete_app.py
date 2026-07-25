"""Reconciler._delete_app: cluster cleanup + in-memory metrics teardown."""

from unittest.mock import Mock, patch

import pytest

from orbital.config import get_settings
from orbital.k8s import metrics
from orbital.k8s.reconciler import Reconciler
from orbital.models import App, AppState, AppType, PendingAction


def make_app(slug="demo") -> App:
    return App(
        id=slug,
        slug=slug,
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=AppState.running,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.delete,
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def test_delete_app_cleans_up_cluster_resources_and_metrics(reconciler):
    app = make_app()
    metrics.store.add(app.id, metrics.Sample(ts=1.0, cpu=0.1, mem=100.0))
    metrics.restart_counts.set(
        app.id, metrics.RestartInfo(count=2, last_reason="Error", last_at=None)
    )

    fake_networking = Mock()
    fake_apps_v1 = Mock()
    fake_core = Mock()
    fake_batch = Mock()
    fake_batch.list_namespaced_job.return_value = Mock(items=[])
    session = Mock()

    try:
        with (
            patch("orbital.k8s.reconciler.client.networking", return_value=fake_networking),
            patch("orbital.k8s.reconciler.client.apps_v1", return_value=fake_apps_v1),
            patch("orbital.k8s.reconciler.client.core", return_value=fake_core),
            patch("orbital.k8s.reconciler.client.batch", return_value=fake_batch),
        ):
            reconciler._delete_app(session, app)

        fake_networking.delete_namespaced_ingress.assert_called_once_with(
            "app-demo", reconciler.settings.apps_namespace
        )
        fake_apps_v1.delete_namespaced_deployment.assert_called_once_with(
            "app-demo", reconciler.settings.apps_namespace
        )
        fake_core.delete_namespaced_service.assert_called_once_with(
            "app-demo", reconciler.settings.apps_namespace
        )
        fake_core.delete_namespaced_secret.assert_called_once_with(
            "app-demo-secrets", reconciler.settings.apps_namespace
        )
        assert fake_batch.list_namespaced_job.call_count == 2  # builds + scans namespaces
        session.delete.assert_called_once_with(app)
        assert metrics.store.latest(app.id) is None
        assert metrics.restart_counts.get(app.id) is None
    finally:
        metrics.store.drop(app.id)
        metrics.restart_counts.drop(app.id)


def test_delete_app_deletes_matching_jobs(reconciler):
    app = make_app()
    job = Mock()
    job.metadata.name = "build-job-1"

    fake_batch = Mock()
    fake_batch.list_namespaced_job.return_value = Mock(items=[job])
    session = Mock()

    with (
        patch("orbital.k8s.reconciler.client.networking", return_value=Mock()),
        patch("orbital.k8s.reconciler.client.apps_v1", return_value=Mock()),
        patch("orbital.k8s.reconciler.client.core", return_value=Mock()),
        patch("orbital.k8s.reconciler.client.batch", return_value=fake_batch),
    ):
        reconciler._delete_app(session, app)

    assert fake_batch.delete_namespaced_job.call_count == 2  # one per namespace's matching job
    fake_batch.delete_namespaced_job.assert_any_call(
        "build-job-1", reconciler.settings.builds_namespace, propagation_policy="Background"
    )
