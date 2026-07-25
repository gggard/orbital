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


# -- Dockerfile-injection guards (issue #76) --------------------------------
# main_file/output_dir get spliced into generated Dockerfile instruction
# lines (src/orbital/k8s/scripts.py); a '"', backslash or newline could break
# out of the intended instruction and inject arbitrary Dockerfile syntax.


def test_main_file_dockerfile_injection_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "inject",
            "repo_url": "https://github.com/x/y",
            "main_file": '"]\nUSER root\nCMD ["sh',
        },
    )
    assert r.status_code == 422


def test_main_file_path_traversal_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "traversal",
            "repo_url": "https://github.com/x/y",
            "main_file": "../../etc/passwd",
        },
    )
    assert r.status_code == 422


def test_main_file_absolute_path_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={"slug": "absolute", "repo_url": "https://github.com/x/y", "main_file": "/etc/passwd"},
    )
    assert r.status_code == 422


def test_valid_main_file_subdirectory_accepted(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "validmain",
            "repo_url": "https://github.com/x/y",
            "main_file": "app/streamlit_app.py",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["main_file"] == "app/streamlit_app.py"


def test_output_dir_dockerfile_injection_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "staticinject",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "output_dir": 'dist"\nUSER root',
        },
    )
    assert r.status_code == 422


def test_output_dir_traversal_rejected(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "statictraversal",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "output_dir": "../secrets",
        },
    )
    assert r.status_code == 422


def test_valid_output_dir_accepted(client):
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "validoutput",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "output_dir": "build/dist",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["output_dir"] == "build/dist"


def test_build_command_still_allows_arbitrary_shell_syntax(client):
    """build_command intentionally runs arbitrary shell (it's the app's own
    build step) - it must not be charset-restricted like main_file/output_dir,
    only kept from splicing into the Dockerfile as a string literal."""
    r = client.post(
        "/api/v1/apps",
        json={
            "slug": "buildcmd",
            "repo_url": "https://github.com/x/y",
            "app_type": "static",
            "build_command": 'echo "hi" && rm -rf node_modules/.cache',
        },
    )
    assert r.status_code == 201, r.text


def test_update_main_file_dockerfile_injection_rejected(client):
    app_id = make_app(client).json()["id"]
    r = client.patch(
        f"/api/v1/apps/{app_id}",
        json={"main_file": '"]\nUSER root\nCMD ["sh'},
    )
    assert r.status_code == 422


def test_secrets_validation(client):
    app_id = make_app(client).json()["id"]
    bad = client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": "not = ["})
    assert bad.status_code == 422
    ok = client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": 'k = "v"'})
    assert ok.status_code == 202
    assert client.get(f"/api/v1/apps/{app_id}/secrets").text == 'k = "v"'


def test_secrets_encrypted_at_rest(client, tmp_path):
    """The API round-trips the plaintext (above), but the raw DB column must
    never hold it - only ciphertext (issue #73)."""
    import sqlite3

    plaintext = 'db_password = "hunter2"'
    app_id = make_app(client, slug="secretive").json()["id"]
    put = client.put(f"/api/v1/apps/{app_id}/secrets", json={"secrets_toml": plaintext})
    assert put.status_code == 202

    conn = sqlite3.connect(tmp_path / "test.db")
    raw = conn.execute("SELECT secrets_toml FROM apps WHERE id = ?", (app_id,)).fetchone()[0]
    conn.close()

    assert raw != plaintext
    assert "hunter2" not in raw
    assert client.get(f"/api/v1/apps/{app_id}/secrets").text == plaintext


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
    app2_id = make_app(client, "app2").json()["id"]
    client.patch(f"/api/v1/apps/{app2_id}", json={"tags": ["ml", "prod"]})
    app3_id = make_app(client, "app3").json()["id"]
    client.patch(f"/api/v1/apps/{app3_id}", json={"tags": ["prod", "web"]})
    assert client.get("/api/v1/tags").json() == {"tags": ["ml", "prod", "web"]}


def test_tags_endpoint_filters_by_substring(client):
    client.patch(f"/api/v1/apps/{make_app(client).json()['id']}", json={"tags": ["ml", "web"]})
    assert client.get("/api/v1/tags?q=ml").json()["tags"] == ["ml"]
    assert client.get("/api/v1/tags?q=nope").json()["tags"] == []
