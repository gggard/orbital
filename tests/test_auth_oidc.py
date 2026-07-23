"""Console OIDC login/callback/logout endpoints (orbital.api.auth)."""

from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from orbital.config import get_settings

ISSUER = "https://idp.example.com/realms/streamlit"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_OIDC_ISSUER_URL", ISSUER)
    monkeypatch.setenv("ORBITAL_OIDC_CLIENT_ID", "orbital-console")
    monkeypatch.setenv("ORBITAL_OIDC_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("ORBITAL_UI_BASE_URL", "http://console.local:3000")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app, follow_redirects=False) as c:
        yield c
    get_settings.cache_clear()


def test_login_disabled_redirects_straight_to_next(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/t.db")
    with TestClient(app, follow_redirects=False) as c:
        r = c.get("/api/auth/login?next=/foo")
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/foo"
    get_settings.cache_clear()


def test_login_disabled_rejects_external_next(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/t.db")
    with TestClient(app, follow_redirects=False) as c:
        for evil in ("https://evil.example.com/steal", "//evil.example.com", "/\\evil.example.com"):
            r = c.get(f"/api/auth/login?next={evil}")
            assert r.status_code in (302, 307)
            assert r.headers["location"] == "/"
    get_settings.cache_clear()


def test_login_redirects_to_idp_with_state(client):
    r = client.get("/api/auth/login?next=/dashboard")
    assert r.status_code in (302, 307)
    location = r.headers["location"]
    split = urlsplit(location)
    assert location.startswith(f"{ISSUER}/protocol/openid-connect/auth")
    qs = parse_qs(split.query)
    assert qs["client_id"] == ["orbital-console"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["http://console.local:3000/api/auth/callback"]
    assert "state" in qs and len(qs["state"][0]) > 0


def test_login_rejects_external_next(client):
    r = client.get("/api/auth/login?next=https://evil.example.com/steal")
    location = r.headers["location"]
    qs = parse_qs(urlsplit(location).query)
    state = qs["state"][0]
    # the open-redirect is neutralized: post_login_redirect falls back to "/"
    with patch("orbital.api.auth.httpx.post") as mock_post, \
         patch("orbital.api.auth._verify_id_token") as mock_verify:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"id_token": "tok"},
            raise_for_status=lambda: None,
        )
        mock_verify.return_value = {"email": "a@b.com", "groups": []}
        cb = client.get(f"/api/auth/callback?code=abc&state={state}")
    assert cb.headers["location"] == "/"


def test_callback_state_mismatch_400(client):
    client.get("/api/auth/login?next=/x")
    r = client.get("/api/auth/callback?code=abc123&state=wrong-state")
    assert r.status_code == 400


def test_callback_missing_code_400(client):
    client.get("/api/auth/login?next=/x")
    r = client.get("/api/auth/callback?state=whatever")
    assert r.status_code == 400


def test_callback_success_sets_session_and_redirects(client):
    r = client.get("/api/auth/login?next=/apps/42")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]

    with patch("orbital.api.auth.httpx.post") as mock_post, \
         patch("orbital.api.auth._verify_id_token") as mock_verify:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"id_token": "id-token-value"},
            raise_for_status=lambda: None,
        )
        mock_verify.return_value = {
            "email": "alice@example.com",
            "groups": ["data-team", 123, "admins"],
        }
        cb = client.get(f"/api/auth/callback?code=abc123&state={state}")

    assert cb.status_code in (302, 307)
    assert cb.headers["location"] == "/apps/42"

    me = client.get("/api/v1/me")
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["groups"] == ["data-team", "admins"]


def test_callback_token_endpoint_error_502(client):
    r = client.get("/api/auth/login?next=/x")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]

    with patch("orbital.api.auth.httpx.post") as mock_post:
        mock_post.return_value = Mock(
            status_code=400,
            raise_for_status=Mock(
                side_effect=httpx.HTTPStatusError(
                    "bad request", request=Mock(), response=Mock(status_code=400)
                )
            ),
        )
        cb = client.get(f"/api/auth/callback?code=abc123&state={state}")
    assert cb.status_code == 502


def test_callback_bad_id_token_502(client):
    r = client.get("/api/auth/login?next=/x")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]

    import jwt as pyjwt

    with patch("orbital.api.auth.httpx.post") as mock_post, \
         patch("orbital.api.auth._verify_id_token") as mock_verify:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"id_token": "bad"},
            raise_for_status=lambda: None,
        )
        mock_verify.side_effect = pyjwt.PyJWTError("bad signature")
        cb = client.get(f"/api/auth/callback?code=abc123&state={state}")
    assert cb.status_code == 502


def test_logout_without_session_redirects_home(client):
    r = client.get("/api/auth/logout")
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "http://console.local:3000/"


def test_logout_disabled_redirects_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/t2.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_BASE_URL", "http://console.local:3000")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/t2.db")
    with TestClient(app, follow_redirects=False) as c:
        r = c.get("/api/auth/logout")
    assert r.headers["location"] == "http://console.local:3000/"
    get_settings.cache_clear()


def test_logout_with_active_session_hits_idp_logout(client):
    r = client.get("/api/auth/login?next=/x")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    with patch("orbital.api.auth.httpx.post") as mock_post, \
         patch("orbital.api.auth._verify_id_token") as mock_verify:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"id_token": "id-token-value"},
            raise_for_status=lambda: None,
        )
        mock_verify.return_value = {"email": "alice@example.com", "groups": []}
        client.get(f"/api/auth/callback?code=abc123&state={state}")

    logout = client.get("/api/auth/logout")
    location = logout.headers["location"]
    assert location.startswith(f"{ISSUER}/protocol/openid-connect/logout")
    qs = parse_qs(urlsplit(location).query)
    assert qs["id_token_hint"] == ["id-token-value"]
    assert qs["post_logout_redirect_uri"] == ["http://console.local:3000/"]

    # session was cleared: /me now 401s
    assert client.get("/api/v1/me").status_code == 401
