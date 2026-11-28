"""Contract tests: CLI commands against the real control-plane API,
in-process (reconciler disabled, auth disabled, SQLite). They catch drift
between the CLI and the API in the PR that causes it.

Skipped unless the `orbital` server package is importable
(`make cli-install` installs both).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("orbital.k8s", reason="control-plane package not installed")

from cryptography.fernet import Fernet  # noqa: E402  (server dependency)
from fastapi.testclient import TestClient  # noqa: E402

from orbital_cli import client as client_mod  # noqa: E402


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "false")
    from orbital import db
    from orbital.config import get_settings

    get_settings.cache_clear()
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as tc:

        class Shared:
            """The CLI closes its client after each command; keep the
            TestClient (and the app's lifespan) alive across commands."""

            def __getattr__(self, name):
                return getattr(tc, name)

            def close(self):
                pass

        def factory(*, base_url, headers, timeout):
            tc.headers.update(headers)
            return Shared()

        monkeypatch.setattr(client_mod, "http_factory", factory)
        yield tc
    get_settings.cache_clear()


def test_create_list_get_update_delete(cli, server):
    r = cli(
        "apps",
        "create",
        "demo",
        "--repo",
        "https://github.com/x/y",
        "--tag",
        "ML",
        "--private",
        "--hibernate-after-seconds",
        "600",
    )
    assert r.exit_code == 0, r.output
    created = json.loads(r.stdout)
    assert created["slug"] == "demo" and created["public"] is False
    assert created["pending_action"] == "deploy"  # new field the CLI's --wait relies on

    assert cli("-o", "name", "apps", "list").stdout == "demo\n"
    assert json.loads(cli("apps", "get", created["id"]).stdout)["slug"] == "demo"

    r = cli("apps", "update", "demo", "--allowed-group", "sales", "--public")
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["allowed_groups"] == ["sales"]

    assert cli("apps", "create", "demo", "--repo", "r").exit_code == 5  # slug taken
    assert cli("apps", "create", "Bad_Slug", "--repo", "r").exit_code == 6  # 422

    r = cli("apps", "delete", "demo", "--yes")
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout) == {"status": "deleting"}


def test_static_type_rules_enforced_by_server(cli, server):
    r = cli("apps", "create", "site", "--repo", "r", "--type", "static", "--main-file", "a.py")
    assert r.exit_code == 6


def test_lifecycle_conflicts(cli, server):
    cli("apps", "create", "demo", "--repo", "https://github.com/x/y")
    assert cli("deploy", "demo").exit_code == 0  # state "created": accepted
    assert cli("reboot", "demo").exit_code == 5  # not running
    assert cli("wake", "demo").exit_code == 5  # not sleeping
    assert cli("scans", "run", "demo").exit_code == 5  # no image yet


def test_secrets_round_trip(cli, server):
    cli("apps", "create", "demo", "--repo", "https://github.com/x/y")
    assert cli("secrets", "set", "demo", "-f", "-", input='KEY = "v"\n').exit_code == 0
    assert cli("secrets", "get", "demo").stdout == 'KEY = "v"\n'


def test_apply_create_then_update(cli, server, tmp_path):
    path = tmp_path / "orbital.toml"
    path.write_text(
        'slug = "sales"\nrepo_url = "https://github.com/acme/sales"\npublic = false\n'
        'tags = ["Team"]\n[hibernate]\nafter_seconds = 900\n'
    )
    r = cli("apply", "-f", str(path))
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["hibernate_after_seconds"] == 900

    # re-applying the same manifest: no setting changes (tags normalized), only a redeploy
    r = cli("apply", "-f", str(path), "--dry-run")
    plan = json.loads(r.stdout)
    assert plan["action"] == "none", plan
    # (the app is still "created" with its first build pending, so no second deploy)
    assert plan["redeploy"] is False

    path.write_text(path.read_text().replace("public = false", "public = true"))
    r = cli("apply", "-f", str(path))
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["public"] is True


def test_reads(cli, server):
    cli("apps", "create", "demo", "--repo", "https://github.com/x/y")
    assert json.loads(cli("builds", "list", "demo").stdout) == []
    assert json.loads(cli("scans", "list", "demo").stdout) == []
    assert json.loads(cli("analytics", "demo").stdout)["total_views"] == 0
    assert json.loads(cli("whoami").stdout)["role"] == "admin"
    assert json.loads(cli("admin", "overview").stdout)["totals"]["app_count"] == 1
    assert isinstance(json.loads(cli("admin", "activity").stdout), list)
    assert cli("health").exit_code == 0


def test_tokens(cli, server):
    r = cli("tokens", "create", "ci", "--ttl-days", "7")
    assert r.exit_code == 0, r.output
    token = json.loads(r.stdout)
    assert token["token"].startswith("orbpat_")
    assert cli("-o", "name", "tokens", "list").stdout == f"{token['id']}\n"
    assert cli("tokens", "revoke", token["id"], "--yes").exit_code == 0
    assert cli("tokens", "create", "x", "--ttl-days", "10000").exit_code == 6
