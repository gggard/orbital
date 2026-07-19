"""Authz endpoint tests: public bypass, 401 unauthenticated, group allow/deny."""

import pytest
from fastapi.testclient import TestClient

from orbital.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_OAUTH2_PROXY_AUTH_URL", "http://oauth2-proxy.test/oauth2/auth")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")  # .env may enable it
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def make_app(client, slug="app1", public=True, groups=None):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": slug,
            "repo_url": "https://github.com/x/y",
            "public": public,
            "allowed_groups": groups or [],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def fake_session(monkeypatch, authenticated, email="", groups=()):
    from orbital.api import authz

    monkeypatch.setattr(
        authz, "check_session", lambda url, cookie: (authenticated, email, list(groups))
    )


def test_public_app_always_allowed(client):
    app_id = make_app(client, public=True)
    assert client.get(f"/authz/{app_id}").status_code == 200


def test_unknown_app_404(client):
    assert client.get("/authz/nope").status_code == 404


def test_private_unauthenticated_401(client, monkeypatch):
    app_id = make_app(client, public=False, groups=["data-team"])
    fake_session(monkeypatch, authenticated=False)
    assert client.get(f"/authz/{app_id}").status_code == 401


def test_private_any_authenticated_when_no_groups(client, monkeypatch):
    app_id = make_app(client, public=False, groups=[])
    fake_session(monkeypatch, True, "bob@example.com", ["viewers"])
    assert client.get(f"/authz/{app_id}").status_code == 200


def test_private_group_match_200(client, monkeypatch):
    app_id = make_app(client, public=False, groups=["data-team"])
    fake_session(monkeypatch, True, "alice@example.com", ["data-team", "other"])
    assert client.get(f"/authz/{app_id}").status_code == 200


def test_private_group_mismatch_403(client, monkeypatch):
    app_id = make_app(client, public=False, groups=["data-team"])
    fake_session(monkeypatch, True, "bob@example.com", ["viewers"])
    assert client.get(f"/authz/{app_id}").status_code == 403


def test_access_change_does_not_rebuild(client):
    app_id = make_app(client, public=True)
    r = client.patch(f"/api/v1/apps/{app_id}", json={"public": False, "allowed_groups": ["g1"]})
    assert r.status_code == 200
    body = r.json()
    assert body["public"] is False
    assert body["allowed_groups"] == ["g1"]
    # state untouched: no rebuild scheduled for access-only changes
    assert body["state"] == "created"
