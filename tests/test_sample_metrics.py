"""Reconciler._sample_metrics: per-app CPU/mem and restart-count sampling."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from orbital.config import get_settings
from orbital.k8s import metrics
from orbital.k8s.reconciler import Reconciler
from orbital.models import App, AppState, AppType, PendingAction


def make_app(slug="demo", state=AppState.running) -> App:
    return App(
        id=slug,
        slug=slug,
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=state,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    r = Reconciler()
    yield r
    get_settings.cache_clear()
    metrics.store.drop("demo")
    metrics.restart_counts.drop("demo")


def test_sample_metrics_stores_usage_and_restarts(reconciler):
    app = make_app()
    sample = metrics.Sample(ts=1.0, cpu=0.1, mem=100.0)
    last_at = datetime(2026, 1, 1, tzinfo=UTC)
    info = metrics.RestartInfo(count=2, last_reason="Error", last_at=last_at)
    with patch("orbital.k8s.reconciler.metrics.fetch_app_usage", return_value=sample), patch(
        "orbital.k8s.reconciler.metrics.fetch_pod_restarts", return_value=info
    ):
        reconciler._sample_metrics([app])

    assert metrics.store.latest("demo") == sample
    assert metrics.restart_counts.get("demo") == info


def test_sample_metrics_skips_non_running_apps(reconciler):
    app = make_app(state=AppState.sleeping)
    with patch("orbital.k8s.reconciler.metrics.fetch_app_usage") as usage, patch(
        "orbital.k8s.reconciler.metrics.fetch_pod_restarts"
    ) as restarts:
        reconciler._sample_metrics([app])

    usage.assert_not_called()
    restarts.assert_not_called()
    assert metrics.store.latest("demo") is None
    assert metrics.restart_counts.get("demo") is None


def test_sample_metrics_usage_failure_does_not_block_restarts(reconciler):
    app = make_app()
    info = metrics.RestartInfo(count=1, last_reason=None, last_at=None)
    with patch(
        "orbital.k8s.reconciler.metrics.fetch_app_usage", side_effect=RuntimeError("boom")
    ), patch("orbital.k8s.reconciler.metrics.fetch_pod_restarts", return_value=info):
        reconciler._sample_metrics([app])  # must not raise

    assert metrics.store.latest("demo") is None
    assert metrics.restart_counts.get("demo") == info


def test_sample_metrics_restarts_failure_does_not_block_usage(reconciler):
    app = make_app()
    sample = metrics.Sample(ts=1.0, cpu=0.2, mem=200.0)
    with patch("orbital.k8s.reconciler.metrics.fetch_app_usage", return_value=sample), patch(
        "orbital.k8s.reconciler.metrics.fetch_pod_restarts", side_effect=RuntimeError("boom")
    ):
        reconciler._sample_metrics([app])  # must not raise

    assert metrics.store.latest("demo") == sample
    assert metrics.restart_counts.get("demo") is None


def test_sample_metrics_none_results_store_nothing(reconciler):
    app = make_app()
    with patch("orbital.k8s.reconciler.metrics.fetch_app_usage", return_value=None), patch(
        "orbital.k8s.reconciler.metrics.fetch_pod_restarts", return_value=None
    ):
        reconciler._sample_metrics([app])

    assert metrics.store.latest("demo") is None
    assert metrics.restart_counts.get("demo") is None
