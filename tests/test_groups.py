"""Group directory: merge logic, Keycloak flattening, /api/v1/groups endpoint."""

from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from orbital import groups as groups_mod
from orbital.config import Settings, get_settings
from orbital.groups import (
    _fetch_keycloak_groups,
    _flatten,
    _keycloak_groups_cached,
    known_groups,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["admins"]')
    monkeypatch.setenv("ORBITAL_CREATOR_GROUPS", '["data-team"]')
    monkeypatch.setenv("ORBITAL_VIEWER_GROUPS", '["viewers"]')
    monkeypatch.setenv("ORBITAL_KNOWN_GROUPS", '["marketing", "data-team"]')
    monkeypatch.setenv("ORBITAL_GROUPS_FROM_KEYCLOAK", "false")  # .env may enable it
    get_settings.cache_clear()
    groups_mod.clear_cache()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    groups_mod.clear_cache()


def test_flatten_nested_subgroups():
    tree = [
        {"name": "a", "subGroups": [{"name": "a1"}, {"name": "a2", "subGroups": [{"name": "a2x"}]}]},
        {"name": "b"},
        {"noname": True},
    ]
    assert _flatten(tree) == ["a", "a1", "a2", "a2x", "b"]


def test_known_groups_merges_config_sources(client):
    got = known_groups(get_settings())
    assert got == ["admins", "data-team", "marketing", "viewers"]


def test_known_groups_includes_keycloak(client, monkeypatch):
    monkeypatch.setenv("ORBITAL_GROUPS_FROM_KEYCLOAK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        groups_mod, "_fetch_keycloak_groups", lambda s: ["from-idp", "admins"]
    )
    assert "from-idp" in known_groups(get_settings())


def test_known_groups_keycloak_failure_falls_back(client, monkeypatch):
    monkeypatch.setenv("ORBITAL_GROUPS_FROM_KEYCLOAK", "true")
    get_settings.cache_clear()

    def boom(_):
        raise ValueError("no realm")

    monkeypatch.setattr(groups_mod, "_fetch_keycloak_groups", boom)
    assert known_groups(get_settings()) == ["admins", "data-team", "marketing", "viewers"]


def test_groups_endpoint(client):
    body = client.get("/api/v1/groups").json()
    assert body == {"groups": ["admins", "data-team", "marketing", "viewers"]}


def test_groups_endpoint_filters_by_substring(client):
    assert client.get("/api/v1/groups?q=team").json()["groups"] == ["data-team"]
    assert client.get("/api/v1/groups?q=TEAM").json()["groups"] == ["data-team"]
    assert client.get("/api/v1/groups?q=nope").json()["groups"] == []


def test_groups_endpoint_respects_limit(client):
    assert client.get("/api/v1/groups?limit=2").json()["groups"] == ["admins", "data-team"]
    # nonsense limits are clamped, not errors
    assert len(client.get("/api/v1/groups?limit=0").json()["groups"]) == 1
    assert len(client.get("/api/v1/groups?limit=9999").json()["groups"]) == 4


# -- _fetch_keycloak_groups (real HTTP calls, mocked) -----------------------


@pytest.fixture(autouse=True)
def _clear_groups_cache():
    groups_mod.clear_cache()
    yield
    groups_mod.clear_cache()


def _kc_settings(**overrides) -> Settings:
    base = dict(
        oidc_issuer_url="https://idp.example.com/realms/streamlit",
        oidc_client_id="orbital",
        oidc_client_secret="s3cr3t",
    )
    base.update(overrides)
    return Settings(**base)


def test_fetch_keycloak_groups_success():
    token_resp = Mock(json=lambda: {"access_token": "tok"}, raise_for_status=lambda: None)
    groups_resp = Mock(
        json=lambda: [{"name": "a", "subGroups": [{"name": "a1"}]}, {"name": "b"}],
        raise_for_status=lambda: None,
    )
    with patch("orbital.groups.httpx.post", return_value=token_resp) as mock_post, \
         patch("orbital.groups.httpx.get", return_value=groups_resp) as mock_get:
        result = _fetch_keycloak_groups(_kc_settings())
    assert result == ["a", "a1", "b"]
    assert mock_post.call_args.args[0] == (
        "https://idp.example.com/realms/streamlit/protocol/openid-connect/token"
    )
    assert mock_get.call_args.args[0] == (
        "https://idp.example.com/admin/realms/streamlit/groups"
    )
    assert mock_get.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}


def test_fetch_keycloak_groups_bad_issuer_url_raises():
    with pytest.raises(ValueError, match="no /realms/"):
        _fetch_keycloak_groups(_kc_settings(oidc_issuer_url="https://idp.example.com/oops"))


def test_fetch_keycloak_groups_token_error_propagates():
    with patch(
        "orbital.groups.httpx.post", side_effect=httpx.ConnectError("refused")
    ):
        with pytest.raises(httpx.ConnectError):
            _fetch_keycloak_groups(_kc_settings())


def test_keycloak_groups_cached_hits_cache_within_ttl():
    settings = _kc_settings()
    with patch("orbital.groups._fetch_keycloak_groups", return_value=["fresh"]) as mock_fetch:
        first = _keycloak_groups_cached(settings)
        second = _keycloak_groups_cached(settings)
    assert first == ["fresh"]
    assert second == ["fresh"]
    mock_fetch.assert_called_once()


def test_groups_endpoint_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_GROUPS_FROM_KEYCLOAK", "false")
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/t.db")
    with TestClient(app) as c:
        assert c.get("/api/v1/groups").status_code == 401
    get_settings.cache_clear()
