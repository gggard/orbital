"""Shared fixtures for the whole test suite."""

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _secrets_encryption_key(monkeypatch):
    """Settings() refuses to construct without ORBITAL_SECRETS_ENCRYPTION_KEY
    (see config.py). Tests don't exercise key provisioning itself, so supply
    a valid one everywhere by default rather than touching every fixture
    that builds a Settings/TestClient.
    """
    monkeypatch.setenv("ORBITAL_SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """orbital.ratelimit's limiters are module-level singletons that live for
    the whole process (the FastAPI `app` is only constructed once and
    imported repeatedly across test modules), so hits from one test would
    otherwise accumulate and eventually 429 unrelated tests that happen to
    exercise /api/auth/login, /api/auth/callback, or the webhook endpoint.
    Reset before every test for isolation; tests that want to exercise the
    limiter itself set a low limit and make the calls within a single test.
    """
    from orbital.ratelimit import login_limiter, webhook_limiter

    login_limiter.reset()
    webhook_limiter.reset()
