"""Personal API token tests: issuance, revocation, expiry, and the real
Authorization: Bearer verification path (not the get_current_user override)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from orbital.api.security import User, get_current_user
from orbital.config import get_settings

ALICE = User(email="alice@example.com", groups=["data-team"], role="creator")
BOB = User(email="bob@example.com", groups=["viewers"], role="viewer")


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


def issue_token(client, user: User, **body) -> str:
    as_user(client, user)
    r = client.post("/api/v1/me/tokens", json={"name": "ci", **body})
    assert r.status_code == 201
    return r.json()["token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_returns_raw_token_once(client):
    as_user(client, ALICE)
    r = client.post("/api/v1/me/tokens", json={"name": "laptop"})
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("orbpat_")
    assert body["name"] == "laptop"

    listed = client.get("/api/v1/me/tokens").json()
    assert len(listed) == 1
    assert "token" not in listed[0] and "token_hash" not in listed[0]


def test_bearer_token_authenticates_real_endpoint(client):
    token = issue_token(client, ALICE)
    client.app.dependency_overrides.clear()  # exercise the *real* auth path

    r = client.get("/api/v1/apps", headers=bearer(token))
    assert r.status_code == 200

    me = client.get("/api/v1/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["role"] == "creator"


def test_invalid_token_rejected(client):
    client.app.dependency_overrides.clear()
    r = client.get("/api/v1/apps", headers=bearer("orbpat_not-a-real-token"))
    assert r.status_code == 401


def test_ttl_above_max_rejected(client):
    as_user(client, ALICE)
    r = client.post("/api/v1/me/tokens", json={"name": "x", "ttl_days": 9999})
    assert r.status_code == 422


def test_expired_token_rejected(client):
    token = issue_token(client, ALICE, ttl_days=1)
    from orbital import db
    from orbital.models import ApiToken

    with db.session_scope() as session:
        rec = session.query(ApiToken).one()
        rec.expires_at = datetime.now(UTC) - timedelta(days=1)

    client.app.dependency_overrides.clear()
    r = client.get("/api/v1/apps", headers=bearer(token))
    assert r.status_code == 401


def test_revoked_token_rejected(client):
    as_user(client, ALICE)
    token_id = client.post("/api/v1/me/tokens", json={"name": "x"}).json()["id"]
    token = client.post("/api/v1/me/tokens", json={"name": "y"}).json()["token"]
    # revoke the *second* token (the one we'll try to use)
    listed = client.get("/api/v1/me/tokens").json()
    y_id = next(t["id"] for t in listed if t["id"] != token_id)
    assert client.delete(f"/api/v1/me/tokens/{y_id}").status_code == 202

    client.app.dependency_overrides.clear()
    r = client.get("/api/v1/apps", headers=bearer(token))
    assert r.status_code == 401


def test_list_scoped_to_own_tokens(client):
    issue_token(client, ALICE)
    issue_token(client, BOB)

    as_user(client, ALICE)
    assert len(client.get("/api/v1/me/tokens").json()) == 1

    as_user(client, BOB)
    assert len(client.get("/api/v1/me/tokens").json()) == 1


def test_cannot_revoke_others_token(client):
    as_user(client, ALICE)
    token_id = client.post("/api/v1/me/tokens", json={"name": "x"}).json()["id"]

    as_user(client, BOB)
    assert client.delete(f"/api/v1/me/tokens/{token_id}").status_code == 404


def test_role_reresolved_live_groups_snapshotted(client, monkeypatch):
    """Groups are frozen at issuance; role is re-derived from them against
    the *current* mapping, so a mapping change takes effect without reissue."""
    token = issue_token(client, ALICE)  # groups=["data-team"] -> creator
    client.app.dependency_overrides.clear()

    # promote data-team to admin in the role mapping (not alice's own groups)
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["data-team"]')
    get_settings.cache_clear()

    me = client.get("/api/v1/me", headers=bearer(token))
    assert me.json()["role"] == "admin"
