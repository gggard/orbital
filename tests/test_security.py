"""Unit tests for orbital.api.security: role resolution and session-based auth."""

from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from orbital.api.security import User, get_current_user, resolve_role
from orbital.config import Settings, get_settings

# -- resolve_role ------------------------------------------------------------


def _settings(**overrides) -> Settings:
    base = dict(
        admin_groups=["admins"],
        creator_groups=["data-team"],
        viewer_groups=["viewers"],
    )
    base.update(overrides)
    return Settings(**base)


def test_resolve_role_admin_takes_priority():
    settings = _settings()
    assert resolve_role(["admins", "data-team"], settings) == "admin"


def test_resolve_role_creator():
    settings = _settings()
    assert resolve_role(["data-team"], settings) == "creator"


def test_resolve_role_viewer():
    settings = _settings()
    assert resolve_role(["viewers"], settings) == "viewer"


def test_resolve_role_none_for_unmapped_groups():
    settings = _settings()
    assert resolve_role(["random-group"], settings) is None


def test_resolve_role_empty_groups_is_none():
    settings = _settings()
    assert resolve_role([], settings) is None


# -- get_current_user (real session path, not dependency-overridden) --------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["admins"]')
    monkeypatch.setenv("ORBITAL_CREATOR_GROUPS", '["data-team"]')
    monkeypatch.setenv("ORBITAL_VIEWER_GROUPS", '["viewers"]')
    monkeypatch.setenv("ORBITAL_OIDC_ISSUER_URL", "https://idp.example.com/realms/streamlit")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app, follow_redirects=False) as c:
        yield c
    get_settings.cache_clear()


def _login_session(client, email, groups):
    """Drive the real login/callback flow (with the IdP call mocked) to plant a session."""
    r = client.get("/api/auth/login?next=/x")
    state = parse_qs(urlsplit(r.headers["location"]).query)["state"][0]
    with patch("orbital.api.auth.httpx.post") as mock_post, \
         patch("orbital.api.auth._verify_id_token") as mock_verify:
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {"id_token": "tok"},
            raise_for_status=lambda: None,
        )
        mock_verify.return_value = {"email": email, "groups": groups}
        client.get(f"/api/auth/callback?code=abc123&state={state}")


def test_get_current_user_no_session_401(client):
    assert client.get("/api/v1/me").status_code == 401


def test_get_current_user_unmapped_groups_403(client):
    _login_session(client, "eve@example.com", ["nobody"])
    assert client.get("/api/v1/me").status_code == 403


def test_get_current_user_valid_session_resolves_role(client):
    _login_session(client, "alice@example.com", ["data-team"])
    body = client.get("/api/v1/me").json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "creator"


def test_get_current_user_disabled_auth_returns_dev_admin():
    settings = Settings(ui_auth_enabled=False)

    class FakeRequest:
        session: dict = {}

    user = get_current_user(FakeRequest(), settings)
    assert user == User(email="dev@localhost", groups=[], role="admin")
    assert user.is_admin
