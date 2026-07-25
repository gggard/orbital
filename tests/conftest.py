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
