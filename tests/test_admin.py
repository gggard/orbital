"""Admin fleet dashboard: RBAC, overview totals, and the log tail endpoint."""

import logging

import pytest
from fastapi.testclient import TestClient

from orbital.api.security import User, get_current_user
from orbital.config import get_settings
from orbital.k8s.metrics import Sample, store

ADMIN = User(email="carol@example.com", groups=["admins"], role="admin")
CREATOR = User(email="alice@example.com", groups=["data-team"], role="creator")
VIEWER = User(email="bob@example.com", groups=["viewers"], role="viewer")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["admins"]')
    monkeypatch.setenv("ORBITAL_CREATOR_GROUPS", '["data-team"]')
    monkeypatch.setenv("ORBITAL_VIEWER_GROUPS", '["viewers"]')
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        c.app = app
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def as_user(client, user: User):
    client.app.dependency_overrides[get_current_user] = lambda: user


def make_app(client, slug="app1", owner_groups=None):
    body = {"slug": slug, "repo_url": "https://github.com/x/y"}
    if owner_groups is not None:
        body["owner_groups"] = owner_groups
    return client.post("/api/v1/apps", json=body)


# -- RBAC --------------------------------------------------------------------


def test_overview_requires_admin(client):
    as_user(client, VIEWER)
    assert client.get("/api/v1/admin/overview").status_code == 403
    as_user(client, CREATOR)
    assert client.get("/api/v1/admin/overview").status_code == 403
    as_user(client, ADMIN)
    assert client.get("/api/v1/admin/overview").status_code == 200


def test_logs_requires_admin(client):
    as_user(client, VIEWER)
    assert client.get("/api/v1/admin/logs").status_code == 403
    as_user(client, ADMIN)
    assert client.get("/api/v1/admin/logs").status_code == 200


# -- overview totals -----------------------------------------------------


def test_overview_totals_and_rows(client):
    as_user(client, ADMIN)
    a1 = make_app(client, "one", ["data-team"]).json()["id"]
    a2 = make_app(client, "two", ["viewers"]).json()["id"]

    from orbital.db import session_scope
    from orbital.models import App, AppState

    with session_scope() as session:
        for app_id in (a1, a2):
            session.get(App, app_id).state = AppState.running

    store.add(a1, Sample(ts=1.0, cpu=0.1, mem=100 * 2**20))
    store.add(a2, Sample(ts=1.0, cpu=0.2, mem=200 * 2**20))
    try:
        body = client.get("/api/v1/admin/overview").json()
        assert body["totals"]["app_count"] == 2
        assert body["totals"]["running_count"] == 2
        assert body["totals"]["cpu"] == pytest.approx(0.3)
        assert body["totals"]["mem"] == pytest.approx(300 * 2**20)
        assert body["totals"]["cpu_limit"] == pytest.approx(2 * 1.0)  # default app_cpu_limit=1
        rows = {r["slug"]: r for r in body["apps"]}
        assert rows["one"]["cpu"] == pytest.approx(0.1)
        assert rows["one"]["owner_groups"] == ["data-team"]
        assert rows["two"]["mem"] == pytest.approx(200 * 2**20)
    finally:
        store.drop(a1)
        store.drop(a2)


def test_overview_app_without_metrics_reports_none(client):
    as_user(client, ADMIN)
    make_app(client, "quiet")
    body = client.get("/api/v1/admin/overview").json()
    row = body["apps"][0]
    assert row["cpu"] is None
    assert row["mem"] is None


# -- logs ----------------------------------------------------------------


def test_logs_endpoint_returns_buffered_lines(client):
    as_user(client, ADMIN)
    log = logging.getLogger("orbital.k8s.reconciler")
    log.warning("test-admin-log-marker-%s", "xyz")
    body = client.get("/api/v1/admin/logs?tail=50").text
    assert "test-admin-log-marker-xyz" in body


def test_logs_endpoint_empty_reports_placeholder(client):
    as_user(client, ADMIN)
    from orbital import logbuffer

    logbuffer.handler._buf.clear()
    body = client.get("/api/v1/admin/logs").text
    assert body == "[no logs yet]"
