"""Unit tests for pure Settings helper methods (orbital.config)."""

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from orbital.config import Settings


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
