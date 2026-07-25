"""Unit tests for pure Settings helper methods (orbital.config)."""

import logging

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from orbital.config import INSECURE_DEFAULT_SESSION_SECRET, Settings, warn_if_privileged_builds


def test_resolved_buildkit_image_explicit_override():
    s = Settings(buildkit_image="custom/buildkit:latest")
    assert s.resolved_buildkit_image() == "custom/buildkit:latest"


def test_resolved_buildkit_image_rootless_default():
    s = Settings(buildkit_image="", buildkit_rootless=True)
    assert s.resolved_buildkit_image() == "moby/buildkit:rootless"


def test_resolved_buildkit_image_privileged_default():
    s = Settings(buildkit_image="", buildkit_rootless=False)
    assert s.resolved_buildkit_image() == "moby/buildkit:latest"


def test_base_image_for():
    s = Settings(registry_push_url="registry.local:80")
    assert s.base_image_for("3.12") == "registry.local:80/streamlit-base:py3.12"


def test_app_image_pull_vs_push():
    s = Settings(registry_push_url="push.local", registry_pull_prefix="pull.local")
    assert s.app_image("app1", "build1", pull=True) == "pull.local/apps/app1:build1"
    assert s.app_image("app1", "build1", pull=False) == "push.local/apps/app1:build1"


def test_missing_secrets_encryption_key_rejected():
    with pytest.raises(ValidationError, match="ORBITAL_SECRETS_ENCRYPTION_KEY"):
        Settings(secrets_encryption_key="")


def test_malformed_secrets_encryption_key_rejected():
    with pytest.raises(ValidationError, match="not a valid Fernet key"):
        Settings(secrets_encryption_key="not-a-valid-key")


def test_valid_secrets_encryption_key_accepted():
    key = Fernet.generate_key().decode()
    assert Settings(secrets_encryption_key=key).secrets_encryption_key == key


def test_session_secret_default_rejected_when_ui_auth_enabled():
    with pytest.raises(ValidationError, match="insecure default"):
        Settings(ui_auth_enabled=True, session_secret=INSECURE_DEFAULT_SESSION_SECRET)


def test_session_secret_too_short_rejected_when_ui_auth_enabled():
    with pytest.raises(ValidationError, match="too short"):
        Settings(ui_auth_enabled=True, session_secret="short-but-not-the-default")


def test_session_secret_default_allowed_when_ui_auth_disabled():
    s = Settings(ui_auth_enabled=False, session_secret=INSECURE_DEFAULT_SESSION_SECRET)
    assert s.session_secret == INSECURE_DEFAULT_SESSION_SECRET


def test_session_secret_strong_value_accepted_when_ui_auth_enabled():
    s = Settings(ui_auth_enabled=True, session_secret="x" * 32)
    assert s.session_secret == "x" * 32


def test_privileged_buildkit_warns_at_startup(caplog):
    with caplog.at_level(logging.WARNING, logger="orbital.config"):
        warn_if_privileged_builds(Settings(buildkit_rootless=False))
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert "privileged" in caplog.text.lower()
    assert "ORBITAL_BUILDKIT_ROOTLESS" in caplog.text


def test_rootless_buildkit_does_not_warn_at_startup(caplog):
    with caplog.at_level(logging.WARNING, logger="orbital.config"):
        warn_if_privileged_builds(Settings(buildkit_rootless=True))
    assert caplog.records == []
