"""Authz endpoint tests: public bypass, 401 unauthenticated, group allow/deny."""

from unittest.mock import Mock, patch

import httpx
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


def test_private_app_503_when_oauth2_proxy_not_configured(client, monkeypatch):
    monkeypatch.setenv("ORBITAL_OAUTH2_PROXY_AUTH_URL", "")
    get_settings.cache_clear()
    app_id = make_app(client, public=False, groups=["data-team"])
    assert client.get(f"/authz/{app_id}").status_code == 503
    get_settings.cache_clear()


# -- check_session (real implementation, unmocked) --------------------------


def test_check_session_valid_response_parses_email_and_groups():
    from orbital.api.authz import check_session

    resp = Mock(
        status_code=202,
        headers={
            "x-auth-request-email": "alice@example.com",
            "x-auth-request-groups": "data-team, viewers ,",
        },
    )
    with patch("orbital.api.authz.httpx.get", return_value=resp) as mock_get:
        authenticated, email, groups = check_session("http://oauth2-proxy/oauth2/auth", "sess=abc")
    assert authenticated is True
    assert email == "alice@example.com"
    assert groups == ["data-team", "viewers"]
    assert mock_get.call_args.kwargs["headers"] == {"Cookie": "sess=abc"}


def test_check_session_non_202_is_unauthenticated():
    from orbital.api.authz import check_session

    resp = Mock(status_code=401, headers={})
    with patch("orbital.api.authz.httpx.get", return_value=resp):
        assert check_session("http://oauth2-proxy/oauth2/auth", "") == (False, "", [])


def test_check_session_proxy_unreachable_is_unauthenticated():
    from orbital.api.authz import check_session

    with patch("orbital.api.authz.httpx.get", side_effect=httpx.ConnectError("refused")):
        assert check_session("http://oauth2-proxy/oauth2/auth", "") == (False, "", [])


def test_access_change_does_not_rebuild(client):
    app_id = make_app(client, public=True)
    r = client.patch(f"/api/v1/apps/{app_id}", json={"public": False, "allowed_groups": ["g1"]})
    assert r.status_code == 200
    body = r.json()
    assert body["public"] is False
    assert body["allowed_groups"] == ["g1"]
    # state untouched: no rebuild scheduled for access-only changes
    assert body["state"] == "created"
