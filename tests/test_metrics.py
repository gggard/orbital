"""Metrics: quantity parsing, ring-buffer store, and the metrics endpoint."""

import pytest
from fastapi.testclient import TestClient

from streamlit_host.config import get_settings
from streamlit_host.k8s.metrics import MetricsStore, Sample, parse_quantity, store


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
    # limits reflect platform config defaults (1 cpu / 2Gi)
    assert body["limits"]["cpu"] == 1.0
    assert body["limits"]["mem"] == 2 * 2**30


def test_metrics_endpoint_with_samples(client):
    app_id = _make_app(client)
    store.add(app_id, Sample(ts=100.0, cpu=0.05, mem=50 * 2**20))
    store.add(app_id, Sample(ts=115.0, cpu=0.07, mem=60 * 2**20))
    try:
        body = client.get(f"/api/v1/apps/{app_id}/metrics").json()
        assert body["available"] is True
        assert len(body["series"]) == 2
        assert body["current"]["cpu"] == pytest.approx(0.07)
        assert body["current"]["mem"] == pytest.approx(60 * 2**20)
        assert body["series"][0]["t"] == 100.0
    finally:
        store.drop(app_id)


def test_metrics_endpoint_unknown_app(client):
    assert client.get("/api/v1/apps/nope/metrics").status_code == 404
