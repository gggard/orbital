"""Regression tests for the session cookie's Secure attribute (issue #75)."""

import sys

from fastapi.testclient import TestClient

from orbital.config import get_settings


def _login_response(tmp_path, monkeypatch, *, session_cookie_secure: bool):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("ORBITAL_OIDC_ISSUER_URL", "https://idp.example.com/realms/streamlit")
    monkeypatch.setenv(
        "ORBITAL_SESSION_COOKIE_SECURE", "true" if session_cookie_secure else "false"
    )
    get_settings.cache_clear()
    # orbital.main builds SessionMiddleware (and its https_only flag) once at
    # import time, so a cached module from an earlier test would keep
    # whichever value was live on its first import. Drop it so this test's
    # env var is actually the one that gets wired in.
    sys.modules.pop("orbital.main", None)
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    try:
        with TestClient(app, follow_redirects=False) as client:
            # /api/auth/login writes oauth_state into the session, which is
            # enough to trigger a Set-Cookie on the response - no need to
            # drive the full IdP callback for this.
            return client.get("/api/auth/login?next=/x")
    finally:
        get_settings.cache_clear()
        sys.modules.pop("orbital.main", None)


def test_session_cookie_is_secure_by_default(tmp_path, monkeypatch):
    response = _login_response(tmp_path, monkeypatch, session_cookie_secure=True)
    assert "secure" in response.headers["set-cookie"].lower()


def test_session_cookie_omits_secure_when_disabled(tmp_path, monkeypatch):
    response = _login_response(tmp_path, monkeypatch, session_cookie_secure=False)
    assert "secure" not in response.headers["set-cookie"].lower()
