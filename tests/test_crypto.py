"""Unit tests for orbital.crypto (App.secrets_toml encryption at rest)."""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from orbital import crypto
from orbital.config import Settings


def _settings(key: str | None = None) -> Settings:
    return Settings(secrets_encryption_key=key or Fernet.generate_key().decode())


def test_round_trip():
    settings = _settings()
    ciphertext = crypto.encrypt('db_password = "hunter2"', settings)
    assert crypto.decrypt(ciphertext, settings) == 'db_password = "hunter2"'


def test_round_trip_empty_string():
    settings = _settings()
    assert crypto.decrypt(crypto.encrypt("", settings), settings) == ""


def test_ciphertext_differs_from_plaintext():
    settings = _settings()
    plaintext = 'api_key = "sk-abc123"'
    ciphertext = crypto.encrypt(plaintext, settings)
    assert ciphertext != plaintext
    assert plaintext not in ciphertext


def test_tamper_detection():
    settings = _settings()
    ciphertext = crypto.encrypt("secret", settings)
    tampered = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        crypto.decrypt(tampered, settings)


def test_cross_key_isolation():
    settings_a = _settings()
    settings_b = _settings()
    ciphertext = crypto.encrypt("secret", settings_a)
    with pytest.raises(InvalidToken):
        crypto.decrypt(ciphertext, settings_b)
