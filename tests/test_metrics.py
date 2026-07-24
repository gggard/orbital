"""Metrics: quantity parsing, ring-buffer store, and the metrics endpoint."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from orbital.config import Settings, get_settings
from orbital.k8s.metrics import (
    MetricsStore,
    RestartCounts,
    RestartInfo,
    Sample,
    fetch_pod_restarts,
    parse_quantity,
    restart_counts,
    store,
)


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


# -- quantity parsing ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("250m", 0.25),
        ("1", 1.0),
        ("2", 2.0),
        ("12345678n", 0.012345678),
        ("500u", 0.0005),
        ("128974848", 128974848.0),
        ("512Mi", 512 * 2**20),
        ("2Gi", 2 * 2**30),
        ("1Ki", 1024.0),
        ("129M", 129e6),
        ("0", 0.0),
    ],
)
def test_parse_quantity(raw, expected):
    assert parse_quantity(raw) == pytest.approx(expected)


def test_parse_quantity_rejects_garbage():
    with pytest.raises(ValueError):
        parse_quantity("abc")
    with pytest.raises(ValueError):
        parse_quantity("10Zi")


# -- store -----------------------------------------------------------------


def test_store_ring_buffer_and_drop():
    s = MetricsStore(maxlen=3)
    for i in range(5):
        s.add("a", Sample(ts=float(i), cpu=0.1, mem=100.0))
    assert [x.ts for x in s.series("a")] == [2.0, 3.0, 4.0]
    assert s.series("missing") == []
    s.drop("a")
    assert s.series("a") == []


def test_restart_counts_get_set_drop():
    rc = RestartCounts()
    assert rc.get("a") is None
    info = RestartInfo(count=5, last_reason="OOMKilled", last_at=datetime(2026, 1, 1, tzinfo=UTC))
    rc.set("a", info)
    assert rc.get("a") == info
    rc.drop("a")
    assert rc.get("a") is None


# -- fetch_pod_restarts (Core API, mocked) ----------------------------------


def _container_status(restart_count: int, terminated=None):
    return Mock(
        restart_count=restart_count,
        last_state=Mock(terminated=terminated),
    )


def _terminated(reason: str, finished_at: datetime):
    return Mock(reason=reason, finished_at=finished_at)


def _pod(statuses: list):
    return Mock(status=Mock(container_statuses=statuses))


def test_fetch_pod_restarts_sums_counts_and_picks_latest_termination():
    older = _terminated("Error", datetime(2026, 1, 1, tzinfo=UTC))
    newer = _terminated("OOMKilled", datetime(2026, 1, 2, tzinfo=UTC))
    # an even-older termination processed *after* `newer` must not overwrite it
    stale = _terminated("Error", datetime(2025, 12, 31, tzinfo=UTC))
    pods = [
        _pod([_container_status(2, older), _container_status(0)]),
        _pod([_container_status(1, newer), _container_status(1, stale)]),
    ]
    fake_core = Mock()
    fake_core.list_namespaced_pod.return_value = Mock(items=pods)
    with patch("orbital.k8s.metrics.client.core", return_value=fake_core):
        info = fetch_pod_restarts("app1", Settings())
    assert info.count == 4
    assert info.last_reason == "OOMKilled"
    assert info.last_at == newer.finished_at
    fake_core.list_namespaced_pod.assert_called_once_with(
        "streamlit-apps", label_selector="app.orbital.io/app-id=app1"
    )


def test_fetch_pod_restarts_no_pods_returns_none():
    fake_core = Mock()
    fake_core.list_namespaced_pod.return_value = Mock(items=[])
    with patch("orbital.k8s.metrics.client.core", return_value=fake_core):
        assert fetch_pod_restarts("app1", Settings()) is None


def test_fetch_pod_restarts_never_restarted():
    fake_core = Mock()
    fake_core.list_namespaced_pod.return_value = Mock(
        items=[_pod([_container_status(0)])]
    )
    with patch("orbital.k8s.metrics.client.core", return_value=fake_core):
        info = fetch_pod_restarts("app1", Settings())
    assert info.count == 0
    assert info.last_reason is None
    assert info.last_at is None


def test_fetch_pod_restarts_pod_with_no_container_statuses_yet():
    fake_core = Mock()
    fake_core.list_namespaced_pod.return_value = Mock(
        items=[Mock(status=Mock(container_statuses=None))]
    )
    with patch("orbital.k8s.metrics.client.core", return_value=fake_core):
        info = fetch_pod_restarts("app1", Settings())
    assert info.count == 0


# -- endpoint --------------------------------------------------------------


def _make_app(client):
    r = client.post(
        "/api/v1/apps", json={"slug": "metered", "repo_url": "https://github.com/x/y"}
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_metrics_endpoint_empty(client):
    app_id = _make_app(client)
    body = client.get(f"/api/v1/apps/{app_id}/metrics").json()
    assert body["available"] is False
    assert body["current"] is None
    assert body["series"] == []
    assert body["restarts"] is None
    # limits reflect platform config defaults (1 cpu / 2Gi)
    assert body["limits"]["cpu"] == 1.0
    assert body["limits"]["mem"] == 2 * 2**30


def test_metrics_endpoint_with_samples(client):
    app_id = _make_app(client)
    store.add(app_id, Sample(ts=100.0, cpu=0.05, mem=50 * 2**20))
    store.add(app_id, Sample(ts=115.0, cpu=0.07, mem=60 * 2**20))
    restart_counts.set(
        app_id,
        RestartInfo(count=3, last_reason="OOMKilled", last_at=datetime(2026, 1, 2, tzinfo=UTC)),
    )
    try:
        body = client.get(f"/api/v1/apps/{app_id}/metrics").json()
        assert body["available"] is True
        assert len(body["series"]) == 2
        assert body["current"]["cpu"] == pytest.approx(0.07)
        assert body["current"]["mem"] == pytest.approx(60 * 2**20)
        assert body["series"][0]["t"] == 100.0
        assert body["restarts"] == {
            "count": 3,
            "last_reason": "OOMKilled",
            "last_at": "2026-01-02T00:00:00Z",
        }
    finally:
        store.drop(app_id)
        restart_counts.drop(app_id)


def test_metrics_endpoint_unknown_app(client):
    assert client.get("/api/v1/apps/nope/metrics").status_code == 404
