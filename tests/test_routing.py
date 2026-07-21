"""Routing mode tests: subdomain (default) vs path-based (single host)."""

import pytest

from orbital.config import Settings
from orbital.k8s import resources
from orbital.models import App, AppType


def make_app(slug="demo", app_type=AppType.streamlit) -> App:
    return App(
        id="abc123def456",
        slug=slug,
        repo_url="https://github.com/x/y",
        app_type=app_type,
        public=True,
        owner_groups=[],
        allowed_groups=[],
        output_dir=".",
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


def test_static_subdomain_deployment(subdomain):
    app = make_app(app_type=AppType.static)
    c = _container(resources.deployment(app, "img:1", subdomain, "now"))
    assert c["readinessProbe"]["httpGet"]["path"] == "/"
    assert not any(e["name"] == "STREAMLIT_SERVER_BASE_URL_PATH" for e in c["env"])


def test_static_path_deployment_has_no_base_path_env(path_mode):
    app = make_app(app_type=AppType.static)
    c = _container(resources.deployment(app, "img:1", path_mode, "now"))
    # no generic base-path mechanism exists for static apps (see resources.deployment)
    assert not any(e["name"] == "STREAMLIT_SERVER_BASE_URL_PATH" for e in c["env"])
    assert c["readinessProbe"]["httpGet"]["path"] == "/app/demo/"


def test_static_ingress_has_no_websocket_timeouts(subdomain):
    app = make_app(app_type=AppType.static)
    ing = resources.ingress(app, subdomain)
    annotations = ing["metadata"]["annotations"]
    assert "nginx.ingress.kubernetes.io/proxy-read-timeout" not in annotations
    assert "nginx.ingress.kubernetes.io/proxy-send-timeout" not in annotations


def test_streamlit_ingress_has_websocket_timeouts(subdomain):
    ing = resources.ingress(make_app(), subdomain)
    annotations = ing["metadata"]["annotations"]
    assert annotations["nginx.ingress.kubernetes.io/proxy-read-timeout"] == "3600"
    assert annotations["nginx.ingress.kubernetes.io/proxy-send-timeout"] == "3600"
