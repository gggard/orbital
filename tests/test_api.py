"""API smoke tests (reconciler disabled, no cluster needed)."""

import pytest
from fastapi.testclient import TestClient

from orbital.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")  # .env may enable it
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def make_app(client, slug="demo"):
    return client.post(
        "/api/v1/apps",
        json={"slug": slug, "repo_url": "https://github.com/x/y", "branch": "main"},
    )


def test_create_and_list(client):
    r = make_app(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "created"
    assert body["slug"] == "demo"
    assert body["webhook_path"].startswith("/webhooks/apps/")
    assert client.get("/api/v1/apps").json()[0]["id"] == body["id"]


def test_duplicate_slug_rejected(client):
    assert make_app(client).status_code == 201
    assert make_app(client).status_code == 409


def test_invalid_slug_rejected(client):
    r = client.post(
        "/api/v1/apps", json={"slug": "Bad_Slug!", "repo_url": "https://github.com/x/y"}
    )
    assert r.status_code == 422


def test_unsupported_python_version(client):
    r = client.post(
        "/api/v1/apps",
        json={"slug": "py", "repo_url": "https://x", "python_version": "2.7"},
    )
    assert r.status_code == 422


def test_secrets_validation(client):
    app_id = make_app(client).json()["id"]
    bad = client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": "not = ["})
    assert bad.status_code == 422
    ok = client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": 'k = "v"'})
    assert ok.status_code == 202
    assert client.get(f"/api/v1/apps/{app_id}/secrets").text == 'k = "v"'


def test_webhook_token(client):
    body = make_app(client).json()
    assert client.post(f"/webhooks/apps/{body['id']}/wrong-token").status_code == 404
    assert client.post(body["webhook_path"]).status_code == 202


def test_delete_marks_deleting(client):
    app_id = make_app(client).json()["id"]
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 202
    assert client.get(f"/api/v1/apps/{app_id}").json()["state"] == "deleting"
