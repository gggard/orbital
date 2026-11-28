"""Command behaviour against a scripted fake API."""

import json
import tomllib

import pytest
from conftest import make_app

from orbital_cli import __version__

APPS = "/api/v1/apps"
APP = f"{APPS}/a1b2c3d4e5f6"


@pytest.fixture
def one_app(api):
    api.on(
        "GET",
        APPS,
        [make_app(), make_app(id="ffffffffffff", slug="other", state="sleeping", tags=["ML"])],
    )
    return api


# -- global behaviour ----------------------------------------------------------------


def test_no_args_shows_help(cli):
    result = cli()
    assert "Usage: orbital" in result.output


def test_json_is_the_default_when_not_a_tty(cli, one_app):
    result = cli("apps", "list")
    assert result.exit_code == 0
    assert [a["slug"] for a in json.loads(result.stdout)] == ["demo", "other"]


def test_table_and_name_output(cli, one_app):
    table = cli("-o", "table", "apps", "list").stdout.splitlines()
    assert table[0].split() == ["SLUG", "TYPE", "STATE", "URL", "UPDATED"]
    assert table[1].startswith("demo")
    assert cli("-o", "name", "apps", "list").stdout == "demo\nother\n"


def test_output_from_env(cli, one_app):
    assert cli("apps", "list", env={"ORBITAL_OUTPUT": "name"}).stdout == "demo\nother\n"


def test_list_filters(cli, one_app):
    assert cli("-o", "name", "apps", "list", "--tag", "ml").stdout == "other\n"
    assert cli("-o", "name", "apps", "list", "--state", "running").stdout == "demo\n"


def test_errors_are_json_on_stderr_with_exit_code(cli, one_app):
    result = cli("apps", "get", "missing")
    assert result.exit_code == 4
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "error": {"code": 4, "http_status": 404, "message": "app 'missing' not found"}
    }
    result = cli("-o", "table", "apps", "get", "missing")
    assert result.stderr.strip() == "error: app 'missing' not found"


def test_token_and_url_are_sent(cli, one_app):
    cli("--url", "https://orb.example", "apps", "list", env={"ORBITAL_TOKEN": "orbpat_x"})
    req = one_app.requests[0]
    assert str(req.url) == "https://orb.example/api/v1/apps"
    assert req.headers["Authorization"] == "Bearer orbpat_x"


def test_token_stdin(cli, one_app):
    cli("--token-stdin", "apps", "list", input="orbpat_piped\n")
    assert one_app.requests[0].headers["Authorization"] == "Bearer orbpat_piped"


def test_unknown_profile(cli):
    result = cli("--profile", "nope", "apps", "list")
    assert result.exit_code == 2
    assert "profile 'nope' not found" in result.stderr


def test_invalid_output_format(cli):
    result = cli("-o", "yaml", "apps", "list")
    assert result.exit_code == 2


# -- apps ----------------------------------------------------------------------------


def test_get_by_slug_or_id(cli, one_app):
    assert json.loads(cli("apps", "get", "demo").stdout)["id"] == "a1b2c3d4e5f6"
    assert json.loads(cli("apps", "get", "ffffffffffff").stdout)["slug"] == "other"
    table = cli("-o", "table", "status", "demo").stdout
    assert "state" in table and "running" in table


def test_create(cli, api):
    api.on(
        "POST",
        APPS,
        (201, make_app(state="created", pending_action="deploy", current_build_id=None)),
    )
    result = cli(
        "apps",
        "create",
        "demo",
        "--repo",
        "https://github.com/x/y",
        "--private",
        "--tag",
        "a",
        "--tag",
        "b",
        "--hibernate-after-seconds",
        "600",
    )
    assert result.exit_code == 0, result.output
    assert api.body("POST", APPS) == {
        "slug": "demo",
        "repo_url": "https://github.com/x/y",
        "app_type": "streamlit",
        "public": False,
        "tags": ["a", "b"],
        "hibernate_after_seconds": 600,
    }
    assert "created demo" in result.stderr


def test_create_with_secrets_and_wait(cli, api, tmp_path):
    secrets = tmp_path / "s.toml"
    secrets.write_text('API_KEY = "x"\n')
    api.on(
        "POST",
        APPS,
        (201, make_app(state="created", pending_action="deploy", current_build_id=None)),
    )
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b1"),
        make_app(state="running", current_build_id="b1"),
    )
    result = cli("apps", "create", "demo", "--repo", "r", "--secrets-file", str(secrets), "--wait")
    assert result.exit_code == 0, result.output
    assert api.body("POST", APPS)["secrets_toml"] == 'API_KEY = "x"\n'
    assert json.loads(result.stdout)["current_build_id"] == "b1"


def test_create_static_rejected_by_server(cli, api):
    api.on("POST", APPS, (422, {"detail": "main_file is only valid for streamlit apps"}))
    result = cli("apps", "create", "s", "--repo", "r", "--type", "static", "--main-file", "a.py")
    assert result.exit_code == 6


def test_update_requires_a_setting(cli, one_app):
    assert cli("apps", "update", "demo").exit_code == 2


def test_update_with_rebuild_waits(cli, one_app):
    one_app.on("PATCH", APP, make_app(branch="dev", pending_action="deploy"))
    one_app.on(
        "GET",
        APP,
        make_app(branch="dev", state="building", current_build_id="b2"),
        make_app(branch="dev", current_build_id="b2"),
    )
    result = cli("apps", "update", "demo", "--branch", "dev", "--wait")
    assert result.exit_code == 0, result.output
    assert one_app.body("PATCH", APP) == {"branch": "dev"}
    assert "rebuild scheduled" in result.stderr
    assert json.loads(result.stdout)["current_build_id"] == "b2"


def test_update_without_rebuild_does_not_wait(cli, one_app):
    one_app.on("PATCH", APP, make_app(public=False))
    result = cli("apps", "update", "demo", "--private", "--allowed-group", "g", "--wait")
    assert result.exit_code == 0
    assert one_app.body("PATCH", APP) == {"public": False, "allowed_groups": ["g"]}
    assert one_app.calls("GET", APP) == []


def test_delete_requires_yes_when_non_interactive(cli, one_app):
    result = cli("apps", "delete", "demo")
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert one_app.calls("DELETE", APP) == []


def test_delete_and_wait(cli, one_app):
    one_app.on("DELETE", APP, (202, {"status": "deleting"}))
    one_app.on("GET", APP, make_app(state="deleting"), (404, {"detail": "app not found"}))
    result = cli("apps", "delete", "demo", "--yes", "--wait")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["state"] == "deleted"


def test_open_prints_url_when_non_interactive(cli, one_app):
    assert cli("apps", "open", "demo").stdout.strip() == "https://demo.apps.example.com"


# -- lifecycle -----------------------------------------------------------------------


def test_deploy_without_wait(cli, one_app):
    one_app.on("POST", f"{APP}/deploy", (202, {"status": "deploy scheduled"}))
    result = cli("deploy", "demo")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"status": "deploy scheduled"}


def test_deploy_conflict(cli, one_app):
    one_app.on("POST", f"{APP}/deploy", (409, {"detail": "a build is already in progress"}))
    result = cli("deploy", "demo")
    assert result.exit_code == 5
    assert "already in progress" in result.stderr


def test_deploy_wait_follow_success(cli, one_app):
    one_app.on("POST", f"{APP}/deploy", (202, {"status": "deploy scheduled"}))
    one_app.on(
        "GET",
        APP,
        make_app(pending_action="deploy"),
        make_app(state="building", current_build_id="b2"),
        make_app(state="running", current_build_id="b2"),
    )
    one_app.on("GET", f"{APP}/builds/b2/logs", "#1 resolving\n", "#1 resolving\n#2 done\n")
    result = cli("deploy", "demo", "--follow", "--timeout", "2m")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["state"] == "running"  # only the final state on stdout
    assert "#2 done" in result.stderr


def test_deploy_wait_failure_exit_8(cli, one_app):
    one_app.on("POST", f"{APP}/deploy", (202, {"status": "deploy scheduled"}))
    one_app.on("GET", APP, make_app(state="build_failed", current_build_id="b2", error="boom"))
    one_app.on("GET", f"{APP}/builds/b2/logs", "Traceback: boom\n")
    result = cli("deploy", "demo", "--wait")
    assert result.exit_code == 8
    assert "Traceback: boom" in result.stderr
    assert json.loads(result.stderr.strip().splitlines()[-1])["error"]["code"] == 8


def test_deploy_wait_timeout_exit_7(cli, one_app):
    one_app.on("POST", f"{APP}/deploy", (202, {"status": "deploy scheduled"}))
    one_app.on("GET", APP, make_app(state="building", current_build_id="b2"))
    result = cli("deploy", "demo", "--wait", "--timeout", "30s")
    assert result.exit_code == 7


def test_invalid_timeout(cli, one_app):
    assert cli("deploy", "demo", "--wait", "--timeout", "soon").exit_code == 2


def test_reboot_and_wake(cli, one_app):
    one_app.on("POST", f"{APP}/reboot", (202, {"status": "reboot scheduled"}))
    one_app.on("GET", APP, make_app(pending_action="reboot"), make_app())
    assert cli("reboot", "demo", "--wait").exit_code == 0

    one_app.on("POST", "/api/v1/apps/ffffffffffff/wake", (202, {"status": "waking"}))
    result = cli("wake", "other")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"status": "waking"}

    one_app.on("POST", f"{APP}/wake", (409, {"detail": "app is not sleeping (state=running)"}))
    assert cli("wake", "demo").exit_code == 5


def test_wait_command(cli, one_app):
    one_app.on("GET", APP, make_app(state="building"), make_app())
    assert cli("wait", "demo").exit_code == 0


# -- logs, builds --------------------------------------------------------------------


def test_logs(cli, one_app):
    one_app.on("GET", f"{APP}/logs", "hello\nworld")
    result = cli("logs", "demo", "--tail", "10")
    assert result.stdout == "hello\nworld\n"
    assert one_app.calls("GET", f"{APP}/logs")[0].url.params["tail"] == "10"
    result = cli("logs", "demo", "-f")
    assert result.stdout == "hello\nworld"
    assert one_app.calls("GET", f"{APP}/logs")[-1].url.params["follow"] == "true"


BUILDS = [
    {
        "id": "b1",
        "app_id": "a",
        "commit_sha": "aaaaaaaaaaaaaaaa",
        "image": None,
        "phase": "succeeded",
        "error": None,
        "created_at": "2026-11-28T09:00:00Z",
        "finished_at": "2026-11-28T09:02:00Z",
    },
    {
        "id": "b2",
        "app_id": "a",
        "commit_sha": "bbbbbbbbbbbbbbbb",
        "image": None,
        "phase": "failed",
        "error": "pip failed\nmore",
        "created_at": "2026-11-28T10:00:00Z",
        "finished_at": None,
    },
]


def test_builds_list_newest_first(cli, one_app):
    one_app.on("GET", f"{APP}/builds", BUILDS)
    assert cli("-o", "name", "builds", "list", "demo").stdout == "b2\nb1\n"
    table = cli("-o", "table", "builds", "list", "demo").stdout
    assert "bbbbbbbbbb " in table and "pip failed" in table and "more" not in table


def test_builds_logs_defaults_to_latest(cli, one_app):
    one_app.on("GET", f"{APP}/builds", BUILDS)
    one_app.on("GET", f"{APP}/builds/b2/logs", "the log")
    assert cli("builds", "logs", "demo").stdout == "the log\n"


def test_builds_logs_no_builds(cli, one_app):
    one_app.on("GET", f"{APP}/builds", [])
    assert cli("builds", "logs", "demo").exit_code == 4


def test_builds_logs_follow_until_failed(cli, one_app):
    running = [{**BUILDS[1], "phase": "running"}]
    one_app.on("GET", f"{APP}/builds", running, running, BUILDS)
    one_app.on("GET", f"{APP}/builds/b2/logs", "a\n", "a\nb\n", "a\nb\nERROR\n")
    result = cli("builds", "logs", "demo", "b2", "-f")
    assert result.exit_code == 8
    assert result.stderr.count("a\n") == 1 and "ERROR" in result.stderr


# -- secrets -------------------------------------------------------------------------


def test_secrets_get(cli, one_app):
    one_app.on("GET", f"{APP}/secrets", 'K = "v"\n')
    assert cli("secrets", "get", "demo").stdout == 'K = "v"\n'


def test_secrets_set_from_stdin(cli, one_app):
    one_app.on("PUT", f"{APP}/secrets", (202, {"status": "secrets updated; app will restart"}))
    result = cli("secrets", "set", "demo", "-f", "-", input='K = "v"\n')
    assert result.exit_code == 0, result.output
    assert one_app.body("PUT", f"{APP}/secrets") == {"secrets_toml": 'K = "v"\n'}


def test_secrets_set_invalid_toml_is_not_sent_or_echoed(cli, one_app):
    result = cli("secrets", "set", "demo", "-f", "-", input="PASSWORD = hunter2\n")
    assert result.exit_code == 2
    assert "hunter2" not in result.stderr
    assert one_app.calls("PUT", f"{APP}/secrets") == []


def test_secrets_set_missing_file(cli, one_app, tmp_path):
    assert cli("secrets", "set", "demo", "-f", str(tmp_path / "nope")).exit_code == 2


# -- metrics, analytics, scans ---------------------------------------------------------


def test_metrics_table(cli, one_app):
    one_app.on(
        "GET",
        f"{APP}/metrics",
        {
            "available": True,
            "limits": {"cpu": 1.0, "mem": 1073741824},
            "current": {"t": 0, "cpu": 0.25, "mem": 268435456},
            "series": [],
            "restarts": {"count": 2, "last_reason": "OOMKilled", "last_at": "2026-11-28T10:00:00Z"},
        },
    )
    out = cli("-o", "table", "metrics", "demo").stdout
    assert "0.250 cores / 1.000 cores" in out
    assert "256 MiB / 1024 MiB" in out
    assert "OOMKilled" in out


def test_metrics_unavailable(cli, one_app):
    one_app.on(
        "GET",
        f"{APP}/metrics",
        {
            "available": False,
            "limits": {"cpu": 1, "mem": 1},
            "current": None,
            "series": [],
            "restarts": None,
        },
    )
    result = cli("-o", "table", "metrics", "demo")
    assert "No metrics yet" in result.stderr
    assert json.loads(cli("metrics", "demo").stdout)["available"] is False


def test_analytics(cli, one_app):
    one_app.on(
        "GET",
        f"{APP}/analytics",
        {
            "total_views": 42,
            "unique_viewers_1d": 1,
            "unique_viewers_7d": 5,
            "unique_viewers_30d": 9,
            "last_viewed_at": None,
            "daily": [],
            "viewers": [],
        },
    )
    assert "42" in cli("-o", "table", "analytics", "demo").stdout


def _scan(sid, status="succeeded", **counts):
    return {
        "id": sid,
        "app_id": "a",
        "build_id": "b1",
        "image": "img",
        "status": status,
        "trivy_version": "0.60",
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "unknown_count": 0,
        "error": None,
        "created_at": "2026-11-28T10:00:00Z",
        "finished_at": None,
        **counts,
    }


def test_scans_list_and_show(cli, one_app):
    one_app.on("GET", f"{APP}/scans", [_scan("s2", high_count=1), _scan("s1")])
    one_app.on(
        "GET",
        f"{APP}/scans/s2/vulnerabilities",
        [
            {
                "vuln_id": "CVE-2",
                "pkg_name": "b",
                "installed_version": "1",
                "fixed_version": None,
                "severity": "low",
                "title": None,
                "target": None,
            },
            {
                "vuln_id": "CVE-1",
                "pkg_name": "a",
                "installed_version": "1",
                "fixed_version": "2",
                "severity": "high",
                "title": "bad",
                "target": None,
            },
        ],
    )
    assert cli("-o", "name", "scans", "list", "demo").stdout == "s2\ns1\n"
    assert cli("-o", "name", "scans", "show", "demo").stdout == "CVE-1\nCVE-2\n"
    assert cli("-o", "name", "scans", "show", "demo", "--severity", "high").stdout == "CVE-1\n"


def test_scans_show_no_scans(cli, one_app):
    one_app.on("GET", f"{APP}/scans", [])
    assert cli("scans", "show", "demo").exit_code == 4


def test_scans_run_fail_on(cli, one_app):
    one_app.on(
        "GET",
        f"{APP}/scans",
        [_scan("s1")],
        [_scan("s1")],
        [_scan("s2", "succeeded", critical_count=1)],
    )
    one_app.on("POST", f"{APP}/scan", (202, {"status": "scan scheduled"}))
    result = cli("scans", "run", "demo", "--fail-on", "high")
    assert result.exit_code == 8
    assert "1 vulnerability at or above high" in result.stderr
    assert json.loads(result.stdout)["id"] == "s2"


def test_scans_run_passes_gate(cli, one_app):
    one_app.on("GET", f"{APP}/scans", [], [_scan("s1", low_count=3)])
    one_app.on("POST", f"{APP}/scan", (202, {"status": "scan scheduled"}))
    assert cli("scans", "run", "demo", "--fail-on", "high").exit_code == 0


def test_scans_run_no_wait(cli, one_app):
    one_app.on("GET", f"{APP}/scans", [])
    one_app.on("POST", f"{APP}/scan", (409, {"detail": "app has no deployed image yet"}))
    assert cli("scans", "run", "demo").exit_code == 5


# -- tokens, admin -------------------------------------------------------------------


def test_tokens(cli, api):
    api.on(
        "GET",
        "/api/v1/me/tokens",
        [
            {
                "id": "t1",
                "name": "ci",
                "created_at": "2026-11-01",
                "expires_at": "2026-12-01T00:00:00Z",
                "last_used_at": None,
                "revoked_at": None,
            }
        ],
    )
    assert "ci" in cli("-o", "table", "tokens", "list").stdout

    api.on(
        "POST",
        "/api/v1/me/tokens",
        (
            201,
            {
                "id": "t2",
                "name": "gh",
                "token": "orbpat_new",
                "created_at": "x",
                "expires_at": "2026-12-28T00",
            },
        ),
    )
    result = cli("-o", "table", "tokens", "create", "gh", "--ttl-days", "30")
    assert result.stdout == "orbpat_new\n"  # only the secret on stdout: pipeable
    assert "won't be shown again" in result.stderr
    assert api.body("POST", "/api/v1/me/tokens") == {"name": "gh", "ttl_days": 30}

    assert cli("tokens", "revoke", "t2").exit_code == 2
    api.on("DELETE", "/api/v1/me/tokens/t2", (202, {"status": "revoked"}))
    assert cli("tokens", "revoke", "t2", "--yes").exit_code == 0


def test_admin(cli, api):
    api.on(
        "GET",
        "/api/v1/admin/overview",
        {
            "totals": {"app_count": 1, "running_count": 1, "cpu": 0.5, "mem": 2**30},
            "apps": [
                {
                    **make_app(),
                    "cpu": 0.5,
                    "mem": 2**29,
                    "restarts": 0,
                    "cpu_series": [],
                    "mem_series": [],
                }
            ],
        },
    )
    result = cli("-o", "table", "admin", "overview")
    assert "1 apps, 1 running" in result.stderr and "demo" in result.stdout
    assert cli("-o", "name", "admin", "overview").stdout == "demo\n"

    api.on(
        "GET",
        "/api/v1/admin/activity",
        [
            {
                "id": "e",
                "slug": "demo",
                "text": "created",
                "level": "info",
                "actor": "me",
                "created_at": "2026-11-28T10:00:00Z",
            }
        ],
    )
    assert "created" in cli("-o", "table", "admin", "activity", "--limit", "5").stdout
    assert api.calls("GET", "/api/v1/admin/activity")[0].url.params["limit"] == "5"

    api.on("GET", "/api/v1/admin/logs", "cp log")
    assert cli("admin", "logs").stdout == "cp log\n"

    api.on("GET", "/api/v1/admin/scans", (403, {"detail": "admin role required"}))
    assert cli("admin", "scans").exit_code == 3


# -- auth ------------------------------------------------------------------------------

ME = {
    "authenticated": True,
    "auth_enabled": True,
    "email": "alice@example.com",
    "groups": ["devs"],
    "role": "creator",
    "can_create": True,
    "can_publish": True,
}


def test_login_stores_token(cli, api, isolated_env):
    api.on("GET", "/api/v1/me", ME)
    result = cli(
        "--url",
        "https://orb.example",
        "--profile",
        "prod",
        "-o",
        "table",
        "login",
        "--token-stdin",
        input="orbpat_abc\n",
    )
    assert result.exit_code == 0, result.output
    assert "Logged in as alice@example.com (creator)" in result.stderr
    assert api.requests[0].headers["Authorization"] == "Bearer orbpat_abc"
    data = tomllib.loads(isolated_env.read_text())
    assert data["profiles"]["prod"] == {"url": "https://orb.example", "token": "orbpat_abc"}

    # later commands use the stored profile
    api.on("GET", APPS, [])
    cli("apps", "list")
    assert api.requests[-1].headers["Authorization"] == "Bearer orbpat_abc"
    assert str(api.requests[-1].url).startswith("https://orb.example/")

    assert cli("logout").exit_code == 0
    assert "token" not in tomllib.loads(isolated_env.read_text())["profiles"]["prod"]


def test_login_bad_token_is_not_saved(cli, api, isolated_env):
    api.on("GET", "/api/v1/me", (401, {"detail": "invalid or expired token"}))
    result = cli("login", "--token-stdin", input="orbpat_bad\n")
    assert result.exit_code == 3
    assert not isolated_env.exists()


def test_login_needs_a_terminal_or_stdin(cli):
    assert cli("login").exit_code == 2


def test_login_rejects_global_token_stdin(cli):
    assert cli("--token-stdin", "login", input="x\n").exit_code == 2


def test_login_auth_disabled_platform(cli, api, isolated_env):
    api.on("GET", "/api/v1/me", {**ME, "auth_enabled": False, "role": "admin"})
    result = cli("-o", "table", "login", "--token-stdin", input="\n")
    assert result.exit_code == 0
    assert "auth disabled" in result.stderr
    assert "token" not in tomllib.loads(isolated_env.read_text())["profiles"]["default"]


def test_whoami(cli, api):
    api.on("GET", "/api/v1/me", ME)
    assert json.loads(cli("whoami").stdout)["email"] == "alice@example.com"
    assert "creator" in cli("-o", "table", "whoami").stdout


# -- misc ------------------------------------------------------------------------------


def test_version_and_health(cli, api):
    api.on("GET", "/healthz", {"status": "ok", "version": "0.1.0"})
    assert json.loads(cli("version").stdout) == {
        "cli": __version__,
        "platform": "0.1.0",
        "url": "http://localhost:8000",
    }
    assert "ok" in cli("-o", "table", "health").stdout


def test_version_when_unreachable(cli, api):
    api.on("GET", "/healthz", (503, {"detail": "down"}))
    assert "unreachable" in cli("-o", "table", "version").stdout
    assert cli("health").exit_code == 1


def test_completion(cli):
    result = cli("completion", "bash")
    assert result.exit_code == 0
    assert "_ORBITAL_COMPLETE" in result.stdout


def test_version_flag(cli):
    result = cli("--version")
    assert result.exit_code == 0
    assert result.stdout == f"orbital-cli {__version__}\n"
