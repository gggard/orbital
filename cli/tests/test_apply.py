import json

import pytest
from conftest import make_app

APPS = "/api/v1/apps"
APP = f"{APPS}/a1b2c3d4e5f6"


@pytest.fixture
def manifest_file(tmp_path):
    def write(text: str):
        path = tmp_path / "orbital.toml"
        path.write_text(text)
        return str(path)

    return write


BASE = 'slug = "demo"\nrepo_url = "https://github.com/x/y"\n'


def test_dry_run_create_changes_nothing(cli, api, manifest_file):
    api.on("GET", APPS, [])
    result = cli("apply", "-f", manifest_file(BASE + "public = false\n"), "--dry-run")
    assert result.exit_code == 0, result.output
    plan = json.loads(result.stdout)
    assert plan["action"] == "create"
    assert plan["changes"]["public"] == {"from": None, "to": False}
    assert [r.method for r in api.requests] == ["GET"]


def test_dry_run_table(cli, api, manifest_file):
    api.on("GET", APPS, [make_app()])
    result = cli(
        "-o", "table", "apply", "-f", manifest_file(BASE + "public = false\n"), "--dry-run"
    )
    assert result.stdout.splitlines() == [
        "app demo: update",
        "  public  true -> false",
        "  then: redeploy (branch main)",
    ]


def test_create(cli, api, manifest_file):
    api.on("GET", APPS, [])
    api.on(
        "POST",
        APPS,
        (201, make_app(state="created", pending_action="deploy", current_build_id=None)),
    )
    result = cli("apply", "-f", manifest_file(BASE + "[hibernate]\nafter_seconds = 600\n"))
    assert result.exit_code == 0, result.output
    assert api.body("POST", APPS) == {
        "slug": "demo",
        "repo_url": "https://github.com/x/y",
        "app_type": "streamlit",
        "hibernate_after_seconds": 600,
    }
    assert api.calls("POST", f"{APP}/deploy") == []  # creation builds by itself
    assert "app demo: create" in result.stderr


def test_create_and_wait(cli, api, manifest_file):
    api.on("GET", APPS, [])
    api.on(
        "POST",
        APPS,
        (201, make_app(state="created", pending_action="deploy", current_build_id=None)),
    )
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b1"),
        make_app(current_build_id="b1"),
    )
    result = cli("apply", "-f", manifest_file(BASE), "--wait")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["current_build_id"] == "b1"


def test_update_patches_changes_then_redeploys(cli, api, manifest_file):
    api.on("GET", APPS, [make_app()])
    api.on("PATCH", APP, make_app(public=False))
    api.on("POST", f"{APP}/deploy", (202, {"status": "deploy scheduled"}))
    api.on(
        "GET",
        APP,
        make_app(public=False, pending_action="deploy"),
        make_app(public=False, current_build_id="b2"),
    )
    result = cli("apply", "-f", manifest_file(BASE + "public = false\n"), "--wait")
    assert result.exit_code == 0, result.output
    assert api.body("PATCH", APP) == {"public": False}
    assert len(api.calls("POST", f"{APP}/deploy")) == 1


def test_rebuild_field_change_does_not_double_deploy(cli, api, manifest_file):
    api.on("GET", APPS, [make_app()])
    api.on("PATCH", APP, make_app(branch="dev", pending_action="deploy"))
    result = cli("apply", "-f", manifest_file(BASE + 'branch = "dev"\n'))
    assert result.exit_code == 0, result.output
    assert api.calls("POST", f"{APP}/deploy") == []


def test_unchanged_no_redeploy_makes_no_writes(cli, api, manifest_file):
    api.on("GET", APPS, [make_app()])
    result = cli("apply", "-f", manifest_file(BASE), "--no-redeploy")
    assert result.exit_code == 0
    assert [r.method for r in api.requests] == ["GET"]
    assert json.loads(result.stdout)["slug"] == "demo"


def test_already_building_waits_for_that_build(cli, api, manifest_file):
    api.on("GET", APPS, [make_app(state="building", current_build_id="b2")])
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b2"),
        make_app(current_build_id="b2"),
    )
    result = cli("apply", "-f", manifest_file(BASE), "--wait")
    assert result.exit_code == 0, result.output
    assert api.calls("POST", f"{APP}/deploy") == []
    assert "already in progress" in result.stderr


def test_immutable_change_is_usage_error(cli, api, manifest_file):
    api.on("GET", APPS, [make_app()])
    text = 'slug = "demo"\nrepo_url = "https://github.com/other/z"\n'
    result = cli("apply", "-f", manifest_file(text))
    assert result.exit_code == 2
    assert [r.method for r in api.requests] == ["GET"]


def test_invalid_manifest_fails_before_any_request(cli, api, manifest_file):
    result = cli("apply", "-f", manifest_file('slug = "demo"\n'))
    assert result.exit_code == 2
    assert api.requests == []


def test_default_manifest_path(cli, api, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli("apply").exit_code == 2  # orbital.toml missing
    (tmp_path / "orbital.toml").write_text(BASE)
    api.on("GET", APPS, [make_app()])
    assert cli("apply", "--dry-run").exit_code == 0
