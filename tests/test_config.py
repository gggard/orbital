"""Unit tests for pure Settings helper methods (orbital.config)."""

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
