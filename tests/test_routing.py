"""Routing mode tests: subdomain (default) vs path-based (single host)."""

import pytest

from orbital.config import Settings
from orbital.k8s import resources
from orbital.models import App


def make_app(slug="demo") -> App:
    return App(
        id="abc123def456",
        slug=slug,
        repo_url="https://github.com/x/y",
        public=True,
        owner_groups=[],
        allowed_groups=[],
    )


@pytest.fixture
def subdomain() -> Settings:
    return Settings(apps_domain="apps.example.com", _env_file=None)


@pytest.fixture
def path_mode() -> Settings:
    return Settings(
        routing_mode="path", apps_domain="apps.example.com", _env_file=None
    )


def test_subdomain_urls(subdomain):
    assert subdomain.app_url("demo") == "http://demo.apps.example.com"
    assert subdomain.base_url_path("demo") == ""


def test_path_urls(path_mode):
    assert path_mode.app_url("demo") == "http://apps.example.com/app/demo/"
    assert path_mode.base_url_path("demo") == "/app/demo"


def test_path_url_with_port():
    s = Settings(
        routing_mode="path", apps_domain="apps.example.com", apps_url_port=8090,
        _env_file=None,
    )
    assert s.app_url("demo") == "http://apps.example.com:8090/app/demo/"


def test_subdomain_ingress(subdomain):
    ing = resources.ingress(make_app(), subdomain)
    rule = ing["spec"]["rules"][0]
    assert rule["host"] == "demo.apps.example.com"
    assert rule["http"]["paths"][0]["path"] == "/"


def test_path_ingress(path_mode):
    ing = resources.ingress(make_app(), path_mode)
    rule = ing["spec"]["rules"][0]
    assert rule["host"] == "apps.example.com"
    assert rule["http"]["paths"][0]["path"] == "/app/demo"


def _container(dep):
    return dep["spec"]["template"]["spec"]["containers"][0]


def test_subdomain_deployment_plain(subdomain):
    c = _container(resources.deployment(make_app(), "img:1", subdomain, "now"))
    assert {"name": "STREAMLIT_SERVER_BASE_URL_PATH", "value": "/app/demo"} not in c["env"]
    assert c["readinessProbe"]["httpGet"]["path"] == "/_stcore/health"


def test_path_deployment_base_url(path_mode):
    c = _container(resources.deployment(make_app(), "img:1", path_mode, "now"))
    assert {"name": "STREAMLIT_SERVER_BASE_URL_PATH", "value": "/app/demo"} in c["env"]
    assert c["readinessProbe"]["httpGet"]["path"] == "/app/demo/_stcore/health"
    assert c["livenessProbe"]["httpGet"]["path"] == "/app/demo/_stcore/health"
