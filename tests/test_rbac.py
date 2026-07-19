"""Management-plane RBAC tests: login gate, visibility, role permissions."""

import pytest
from fastapi.testclient import TestClient

from orbital.api.security import User, get_current_user
from orbital.config import get_settings

ADMIN = User(email="carol@example.com", groups=["admins"], role="admin")
CREATOR = User(email="alice@example.com", groups=["data-team"], role="creator")
VIEWER = User(email="bob@example.com", groups=["viewers"], role="viewer")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["admins"]')
    monkeypatch.setenv("ORBITAL_CREATOR_GROUPS", '["data-team"]')
    monkeypatch.setenv("ORBITAL_VIEWER_GROUPS", '["viewers"]')
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        c.app = app
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def as_user(client, user: User):
    client.app.dependency_overrides[get_current_user] = lambda: user


def make_app(client, slug="app1", owner_groups=None):
    body = {"slug": slug, "repo_url": "https://github.com/x/y"}
    if owner_groups is not None:
        body["owner_groups"] = owner_groups
    return client.post("/api/v1/apps", json=body)


# -- login gate ------------------------------------------------------------


def test_unauthenticated_401(client):
    assert client.get("/api/v1/apps").status_code == 401
    assert client.get("/api/v1/me").status_code == 401


def test_me_reports_role(client):
    as_user(client, CREATOR)
    me = client.get("/api/v1/me").json()
    assert me["role"] == "creator" and me["can_create"] is True
    as_user(client, VIEWER)
    me = client.get("/api/v1/me").json()
    assert me["role"] == "viewer" and me["can_create"] is False


# -- creation --------------------------------------------------------------


def test_viewer_cannot_create(client):
    as_user(client, VIEWER)
    assert make_app(client).status_code == 403


def test_creator_creates_with_own_groups(client):
    as_user(client, CREATOR)
    r = make_app(client)
    assert r.status_code == 201
    assert r.json()["owner_groups"] == ["data-team"]


def test_creator_cannot_create_without_own_owner_group(client):
    as_user(client, CREATOR)
    assert make_app(client, owner_groups=["admins"]).status_code == 403


def test_admin_sets_any_owner_groups(client):
    as_user(client, ADMIN)
    r = make_app(client, owner_groups=["data-team", "viewers"])
    assert r.status_code == 201


# -- visibility ------------------------------------------------------------


def test_visibility_scoped_by_owner_groups(client):
    as_user(client, ADMIN)
    a1 = make_app(client, "one", ["data-team"]).json()["id"]
    a2 = make_app(client, "two", ["viewers"]).json()["id"]

    as_user(client, CREATOR)
    slugs = [a["slug"] for a in client.get("/api/v1/apps").json()]
    assert slugs == ["one"]
    assert client.get(f"/api/v1/apps/{a2}").status_code == 404  # invisible, not 403

    as_user(client, VIEWER)
    slugs = [a["slug"] for a in client.get("/api/v1/apps").json()]
    assert slugs == ["two"]

    as_user(client, ADMIN)
    assert len(client.get("/api/v1/apps").json()) == 2
    assert client.get(f"/api/v1/apps/{a1}").status_code == 200


# -- public sharing policy -------------------------------------------------


@pytest.fixture
def restricted(client, monkeypatch):
    monkeypatch.setenv("ORBITAL_PUBLIC_SHARING_GROUPS", '["marketing"]')
    get_settings.cache_clear()
    yield client
    get_settings.cache_clear()


def test_publish_restricted_on_create(restricted):
    as_user(restricted, CREATOR)  # alice: data-team, not marketing
    r = restricted.post(
        "/api/v1/apps",
        json={"slug": "pub", "repo_url": "https://x/y", "public": True},
    )
    assert r.status_code == 403
    assert "restricted" in r.json()["detail"]
    # private creation still fine
    r = restricted.post(
        "/api/v1/apps",
        json={"slug": "priv", "repo_url": "https://x/y", "public": False},
    )
    assert r.status_code == 201


def test_publish_restricted_on_transition(restricted):
    as_user(restricted, CREATOR)
    app_id = restricted.post(
        "/api/v1/apps",
        json={"slug": "priv2", "repo_url": "https://x/y", "public": False},
    ).json()["id"]
    assert restricted.patch(f"/api/v1/apps/{app_id}", json={"public": True}).status_code == 403


def test_publish_allowed_for_member_and_admin(restricted):
    member = User(email="mia@example.com", groups=["data-team", "marketing"], role="creator")
    as_user(restricted, member)
    r = restricted.post(
        "/api/v1/apps",
        json={"slug": "mkt", "repo_url": "https://x/y", "public": True},
    )
    assert r.status_code == 201
    as_user(restricted, ADMIN)
    r = restricted.post(
        "/api/v1/apps",
        json={"slug": "adm", "repo_url": "https://x/y", "public": True},
    )
    assert r.status_code == 201


def test_already_public_app_updates_unblocked(restricted):
    as_user(restricted, ADMIN)
    app_id = restricted.post(
        "/api/v1/apps",
        json={"slug": "was-pub", "repo_url": "https://x/y", "public": True,
              "owner_groups": ["data-team"]},
    ).json()["id"]
    # non-publisher manager can still save with public: true (no transition)
    as_user(restricted, CREATOR)
    r = restricted.patch(f"/api/v1/apps/{app_id}", json={"public": True, "branch": "dev"})
    assert r.status_code == 200
    # and can make it private
    assert restricted.patch(f"/api/v1/apps/{app_id}", json={"public": False}).status_code == 200


def test_me_reports_can_publish(restricted):
    as_user(restricted, CREATOR)
    assert restricted.get("/api/v1/me").json()["can_publish"] is False
    as_user(restricted, ADMIN)
    assert restricted.get("/api/v1/me").json()["can_publish"] is True


# -- role permissions ------------------------------------------------------


def test_viewer_read_only(client):
    as_user(client, ADMIN)
    app_id = make_app(client, "shared", ["data-team", "viewers"]).json()["id"]

    as_user(client, VIEWER)
    assert client.get(f"/api/v1/apps/{app_id}").status_code == 200
    assert client.get(f"/api/v1/apps/{app_id}/builds").status_code == 200
    assert client.get(f"/api/v1/apps/{app_id}/metrics").status_code == 200
    assert client.post(f"/api/v1/apps/{app_id}/deploy").status_code == 403
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 403
    assert client.get(f"/api/v1/apps/{app_id}/secrets").status_code == 403
    assert (
        client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": 'a="b"'}).status_code
        == 403
    )
    assert (
        client.patch(f"/api/v1/apps/{app_id}", json={"public": False}).status_code == 403
    )


def test_creator_manages_owned_app(client):
    as_user(client, CREATOR)
    app_id = make_app(client, "mine").json()["id"]
    assert client.post(f"/api/v1/apps/{app_id}/deploy").status_code in (202, 409)
    assert client.get(f"/api/v1/apps/{app_id}/secrets").status_code == 200
    assert client.patch(f"/api/v1/apps/{app_id}", json={"public": False}).status_code == 200


def test_creator_shares_ownership_with_other_group(client):
    as_user(client, CREATOR)
    app_id = make_app(client, "mine").json()["id"]
    # may add co-owner groups as long as one of their own groups remains
    r = client.patch(f"/api/v1/apps/{app_id}", json={"owner_groups": ["data-team", "viewers"]})
    assert r.status_code == 200
    assert r.json()["owner_groups"] == ["data-team", "viewers"]


def test_creator_cannot_transfer_ownership_entirely(client):
    as_user(client, CREATOR)
    app_id = make_app(client, "mine").json()["id"]
    # dropping all own groups would lock the creator out -> admin-only action
    r = client.patch(f"/api/v1/apps/{app_id}", json={"owner_groups": ["admins"]})
    assert r.status_code == 403


def test_creator_cannot_empty_owner_groups(client):
    as_user(client, CREATOR)
    app_id = make_app(client, "mine").json()["id"]
    assert client.patch(f"/api/v1/apps/{app_id}", json={"owner_groups": []}).status_code == 422


def test_admin_manages_everything(client):
    as_user(client, CREATOR)
    app_id = make_app(client, "mine").json()["id"]
    as_user(client, ADMIN)
    assert client.patch(f"/api/v1/apps/{app_id}", json={"owner_groups": ["viewers"]}).status_code == 200
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 202
