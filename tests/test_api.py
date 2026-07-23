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


def test_webhook_ignored_while_building_or_deleting(client):
    from orbital import db
    from orbital.models import App, AppState, PendingAction

    body = make_app(client).json()
    with db.session_scope() as session:
        app = session.get(App, body["id"])
        app.state = AppState.building

    r = client.post(body["webhook_path"])
    assert r.status_code == 202
    assert r.json()["status"].startswith("ignored")

    with db.session_scope() as session:
        app = session.get(App, body["id"])
        app.state = AppState.running
        app.pending_action = PendingAction.delete

    r = client.post(body["webhook_path"])
    assert r.json()["status"].startswith("ignored")


def test_delete_marks_deleting(client):
    app_id = make_app(client).json()["id"]
    assert client.delete(f"/api/v1/apps/{app_id}").status_code == 202
    assert client.get(f"/api/v1/apps/{app_id}").json()["state"] == "deleting"


# -- tags -------------------------------------------------------------------


def test_create_app_with_tags(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "tagged",
            "repo_url": "https://github.com/x/y",
            "tags": ["ml", "internal"],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["tags"] == ["ml", "internal"]


def test_tags_are_trimmed_and_deduped_case_insensitively(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "dedup",
            "repo_url": "https://x",
            "tags": [" ml ", "ML", "", "  ", "ml", "prod"],
        },
    )
    assert r.status_code == 201, r.text
    # first casing seen wins; blanks dropped; exact re-add ignored
    assert r.json()["tags"] == ["ml", "prod"]


def test_tag_too_long_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={"slug": "longtag", "repo_url": "https://x", "tags": ["x" * 41]},
    )
    assert r.status_code == 422


def test_too_many_tags_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={"slug": "manytags", "repo_url": "https://x", "tags": [f"t{i}" for i in range(21)]},
    )
    assert r.status_code == 422


def test_update_app_tags(client):
    app_id = make_app(client).json()["id"]
    assert client.get(f"/api/v1/apps/{app_id}").json()["tags"] == []
    r = client.patch(f"/api/v1/apps/{app_id}", json={"tags": ["a", "b"]})
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["a", "b"]
    # omitting tags on a later patch leaves them untouched
    r = client.patch(f"/api/v1/apps/{app_id}", json={"branch": "dev"})
    assert r.json()["tags"] == ["a", "b"]
    # explicit empty list clears them
    r = client.patch(f"/api/v1/apps/{app_id}", json={"tags": []})
    assert r.json()["tags"] == []


def test_tags_endpoint_collects_distinct_tags(client):
    make_app(client, "app1").json()
    client.patch(f"/api/v1/apps/{make_app(client, 'app2').json()['id']}", json={"tags": ["ml", "prod"]})
    client.patch(f"/api/v1/apps/{make_app(client, 'app3').json()['id']}", json={"tags": ["prod", "web"]})
    assert client.get("/api/v1/tags").json() == {"tags": ["ml", "prod", "web"]}


def test_tags_endpoint_filters_by_substring(client):
    client.patch(f"/api/v1/apps/{make_app(client).json()['id']}", json={"tags": ["ml", "web"]})
    assert client.get("/api/v1/tags?q=ml").json()["tags"] == ["ml"]
    assert client.get("/api/v1/tags?q=nope").json()["tags"] == []
