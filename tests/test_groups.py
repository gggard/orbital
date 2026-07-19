"""Group directory: merge logic, Keycloak flattening, /api/v1/groups endpoint."""

import pytest
from fastapi.testclient import TestClient

from streamlit_host import groups as groups_mod
from streamlit_host.config import get_settings
from streamlit_host.groups import _flatten, known_groups


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SH_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("SH_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("SH_UI_AUTH_ENABLED", "false")
    monkeypatch.setenv("SH_ADMIN_GROUPS", '["admins"]')
    monkeypatch.setenv("SH_CREATOR_GROUPS", '["data-team"]')
    monkeypatch.setenv("SH_VIEWER_GROUPS", '["viewers"]')
    monkeypatch.setenv("SH_KNOWN_GROUPS", '["marketing", "data-team"]')
    monkeypatch.setenv("SH_GROUPS_FROM_KEYCLOAK", "false")  # .env may enable it
    get_settings.cache_clear()
    groups_mod.clear_cache()
    from streamlit_host import db
    from streamlit_host.main import app

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
    monkeypatch.setenv("SH_GROUPS_FROM_KEYCLOAK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(
        groups_mod, "_fetch_keycloak_groups", lambda s: ["from-idp", "admins"]
    )
    assert "from-idp" in known_groups(get_settings())


def test_known_groups_keycloak_failure_falls_back(client, monkeypatch):
    monkeypatch.setenv("SH_GROUPS_FROM_KEYCLOAK", "true")
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


def test_groups_endpoint_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("SH_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("SH_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("SH_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("SH_GROUPS_FROM_KEYCLOAK", "false")
    get_settings.cache_clear()
    from streamlit_host import db
    from streamlit_host.main import app

    db.init_engine(f"sqlite:///{tmp_path}/t.db")
    with TestClient(app) as c:
        assert c.get("/api/v1/groups").status_code == 401
    get_settings.cache_clear()
