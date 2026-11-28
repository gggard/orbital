"""CI-pipeline and agent scenarios, end to end: the real `orbital` binary
against a real control plane over HTTP (see conftest.py)."""

from __future__ import annotations

MANIFEST = """
slug = "sales"
repo_url = "https://github.com/acme/sales"
branch = "main"
main_file = "app.py"
public = false
allowed_groups = ["sales"]
tags = ["team:sales"]

[hibernate]
after_seconds = 900
"""


def test_ci_pipeline_from_first_deploy_to_delete(orbital, tmp_path):
    manifest = tmp_path / "orbital.toml"
    manifest.write_text(MANIFEST)

    # the job's first run creates the app and blocks until it's live
    first = orbital("apply", "-f", str(manifest), "--wait", "--timeout", "60s")
    assert first.code == 0, first.stderr
    app = first.json
    assert (app["slug"], app["state"], app["public"]) == ("sales", "running", False)
    assert app["current_build_id"]
    assert "app sales: create" in first.stderr

    # nothing changed in the manifest: a push to main still means "ship it"
    plan = orbital("apply", "-f", str(manifest), "--dry-run")
    assert plan.json == {
        "action": "none",
        "slug": "sales",
        "changes": {},
        "redeploy": True,
        "reason": "redeploy (branch main)",
    }
    second = orbital("apply", "-f", str(manifest), "--wait", "--timeout", "60s")
    assert second.code == 0, second.stderr
    assert second.json["current_build_id"] != app["current_build_id"]  # a fresh build

    # a settings change is patched, and only that field
    manifest.write_text(MANIFEST.replace("public = false", "public = true"))
    third = orbital("apply", "-f", str(manifest), "--wait", "--timeout", "60s")
    assert third.code == 0, third.stderr
    assert third.json["public"] is True
    assert "public  false -> true" in third.stderr

    # secrets come from the CI secret store, through stdin
    assert orbital("secrets", "set", "sales", "-f", "-", input='API_KEY = "s3cr3t"\n').code == 0
    assert orbital("secrets", "get", "sales").stdout == 'API_KEY = "s3cr3t"\n'

    # history, status, restart
    builds = orbital("builds", "list", "sales").json
    assert [b["phase"] for b in builds] == ["succeeded"] * 3
    assert orbital("status", "sales").json["state"] == "running"
    assert orbital("reboot", "sales", "--wait", "--timeout", "60s").code == 0
    assert orbital("apps", "list", "-o", "name").stdout == "sales\n"

    # teardown
    gone = orbital("apps", "delete", "sales", "--yes", "--wait", "--timeout", "60s")
    assert gone.code == 0, gone.stderr
    assert gone.json["state"] == "deleted"
    assert orbital("apps", "list", "-o", "name").stdout == ""


def test_failed_build_fails_the_job_with_exit_8(orbital):
    created = orbital(
        "apps",
        "create",
        "broken-app",
        "--repo",
        "https://github.com/x/y",
        "--branch",
        "broken",
        "--wait",
        "--timeout",
        "60s",
    )
    assert created.code == 8
    assert created.error["code"] == 8
    assert "build_failed" in created.error["message"]
    assert "pip install failed" in created.error["message"]

    # once fixed, the next deploy goes through
    assert (
        orbital(
            "apps", "update", "broken-app", "--branch", "main", "--wait", "--timeout", "60s"
        ).code
        == 0
    )


def test_wait_timeout_exit_7_leaves_the_deploy_running(orbital):
    assert orbital("apps", "create", "frozen-app", "--repo", "https://github.com/x/y").code == 0
    result = orbital("deploy", "frozen-app", "--wait", "--timeout", "2s")
    assert result.code == 7
    assert "continues server-side" in result.error["message"]


def test_conflicting_deploy_exit_5_then_wait(orbital, local_platform):
    # "frozen" apps are left alone by the simulated reconciler, so the
    # in-progress build below stays in progress until we finish it
    assert orbital("apps", "create", "frozen-busy", "--repo", "https://github.com/x/y").code == 0
    local_platform.set_state("frozen-busy", "building")
    conflict = orbital("deploy", "frozen-busy")
    assert conflict.code == 5
    assert conflict.error == {
        "code": 5,
        "http_status": 409,
        "message": "a build is already in progress",
    }
    # an agent's follow-up: wait for the running build instead
    local_platform.set_state("frozen-busy", "running")
    assert orbital("wait", "frozen-busy", "--timeout", "30s").code == 0


def test_wake_a_hibernating_app(orbital, local_platform):
    assert (
        orbital(
            "apps",
            "create",
            "sleepy",
            "--repo",
            "https://github.com/x/y",
            "--wait",
            "--timeout",
            "60s",
        ).code
        == 0
    )
    local_platform.set_state("sleepy", "sleeping")
    assert orbital("status", "sleepy").json["state"] == "sleeping"
    woke = orbital("wake", "sleepy", "--wait", "--timeout", "60s")
    assert woke.code == 0, woke.stderr
    assert woke.json["state"] == "running"


def test_agent_conventions(orbital, tmp_path):
    # unknown app: exit 4 and a JSON error, nothing on stdout
    missing = orbital("status", "nope")
    assert (missing.code, missing.stdout) == (4, "")
    assert missing.error["code"] == 4

    # destructive command without --yes in CI: refused, exit 2
    orbital("apps", "create", "keep", "--repo", "https://github.com/x/y")
    refused = orbital("apps", "delete", "keep")
    assert refused.code == 2
    assert orbital("status", "keep").code == 0

    # server-side validation: exit 6
    assert orbital("apps", "create", "Bad_Slug", "--repo", "r").code == 6

    # invalid manifest: exit 2 before any change
    bad = tmp_path / "bad.toml"
    bad.write_text('slug = "x"\nrepo_url = "r"\nsecrets_toml = "k = 1"\n')
    assert orbital("apply", "-f", str(bad)).code == 2

    # table output on request; global options after the subcommand
    table = orbital("apps", "list", "-o", "table").stdout.splitlines()
    assert table[0].split()[:3] == ["SLUG", "TYPE", "STATE"]

    # login against an auth-disabled platform stores the profile, then whoami
    login = orbital("login", "--token-stdin", input="\n")
    assert login.code == 0, login.stderr
    assert orbital("whoami").json["role"] == "admin"
    assert orbital("health").code == 0
