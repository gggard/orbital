import pytest
from conftest import make_app

from orbital_cli import wait
from orbital_cli.client import Client
from orbital_cli.errors import CliError, ExitCode

APP = "/api/v1/apps/a1b2c3d4e5f6"


def client():
    return Client("http://x", None)


def test_new_lines():
    assert wait.new_lines([], ["a", "b"]) == ["a", "b"]
    assert wait.new_lines(["a", "b"], ["a", "b", "c"]) == ["c"]
    assert wait.new_lines(["a", "b", "c"], ["b", "c", "d", "e"]) == ["d", "e"]  # window slid
    assert wait.new_lines(["a"], ["x", "y"]) == ["x", "y"]  # no overlap
    assert wait.new_lines(["a", "b"], ["a", "b"]) == []


def test_poller_times_out(fake_clock):
    poller = wait.Poller(10, "thing")
    with pytest.raises(CliError) as e:
        for _ in range(100):
            poller.tick()
    assert e.value.code == ExitCode.TIMEOUT
    assert "10s waiting for thing" in e.value.message
    assert fake_clock[0] == pytest.approx(10)


def test_rollout_success_waits_for_new_build_not_stale_running(api):
    before = make_app()
    api.on(
        "GET",
        APP,
        make_app(pending_action="deploy"),  # not picked up yet: still "running" on old build
        make_app(state="building", current_build_id="build000002"),
        make_app(state="deploying", current_build_id="build000002"),
        make_app(state="running", current_build_id="build000002"),
    )
    result = wait.wait_for_rollout(client(), before, timeout=60, progress=False)
    assert result["current_build_id"] == "build000002"
    assert len(api.calls("GET", APP)) == 4


def test_rollout_build_failure_prints_log_tail(api, capsys):
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b2"),
        make_app(state="build_failed", current_build_id="b2", error="pip failed"),
    )
    api.on("GET", f"{APP}/builds/b2/logs", "step 1\nERROR: no matching dist\n")
    with pytest.raises(CliError) as e:
        wait.wait_for_rollout(client(), make_app(), timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED
    assert "build_failed: pip failed" in e.value.message
    assert "ERROR: no matching dist" in capsys.readouterr().err


def test_rollout_failure_before_build_started(api):
    # commit resolution failed: no new build, request cleared, app build_failed
    api.on(
        "GET",
        APP,
        make_app(pending_action="deploy"),
        make_app(state="build_failed", error="branch not found"),
    )
    api.on("GET", f"{APP}/builds/build000001/logs", "[no logs available]")
    with pytest.raises(CliError) as e:
        wait.wait_for_rollout(client(), make_app(), timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED
    assert "branch not found" in e.value.message


def test_rollout_previously_failed_app_waits_for_pickup(api):
    before = make_app(state="build_failed", error="old failure")
    api.on(
        "GET",
        APP,
        make_app(state="build_failed", pending_action="deploy"),
        make_app(state="building", current_build_id="b2"),
        make_app(state="running", current_build_id="b2"),
    )
    assert wait.wait_for_rollout(client(), before, timeout=60, progress=False)["state"] == "running"


def test_rollout_legacy_server_without_pending_action(api):
    before = make_app(state="build_failed")
    del before["pending_action"]
    stale = make_app(state="build_failed")
    del stale["pending_action"]
    failed = {**stale, "updated_at": "2026-11-28T11:00:00Z", "error": "boom"}
    api.on("GET", APP, stale, failed)
    api.on("GET", f"{APP}/builds/build000001/logs", "")
    with pytest.raises(CliError) as e:
        wait.wait_for_rollout(client(), before, timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED
    assert len(api.calls("GET", APP)) == 2


def test_rollout_timeout(api):
    api.on("GET", APP, make_app(state="building", current_build_id="b2"))
    with pytest.raises(CliError) as e:
        wait.wait_for_rollout(client(), make_app(), timeout=30, progress=False)
    assert e.value.code == ExitCode.TIMEOUT
    assert "continues server-side" in e.value.message


def test_rollout_follow_streams_new_lines_once(api, capsys):
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b2"),
        make_app(state="building", current_build_id="b2"),
        make_app(state="running", current_build_id="b2"),
    )
    api.on("GET", f"{APP}/builds/b2/logs", "one\n", "one\ntwo\n", "one\ntwo\nthree\n")
    wait.wait_for_rollout(client(), make_app(), timeout=60, follow=True, progress=True)
    err = capsys.readouterr().err
    assert err.count("one") == 1 and "three" in err
    assert "--- build b2 ---" in err
    assert "demo: building" in err and "demo: running" in err


def test_reboot(api):
    api.on(
        "GET",
        APP,
        make_app(pending_action="reboot"),
        make_app(state="deploying"),
        make_app(state="running"),
    )
    assert (
        wait.wait_for_reboot(client(), make_app(), timeout=60, progress=False)["state"] == "running"
    )
    assert len(api.calls("GET", APP)) == 3


def test_reboot_failure(api):
    api.on("GET", APP, make_app(state="deploy_failed", error="CrashLoopBackOff"))
    with pytest.raises(CliError) as e:
        wait.wait_for_reboot(client(), make_app(), timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED


def test_wait_for_state_running_and_deleted(api):
    api.on("GET", APP, make_app(state="sleeping"), make_app(state="deploying"), make_app())
    assert (
        wait.wait_for_state(client(), make_app(), target="running", timeout=60, progress=False)[
            "state"
        ]
        == "running"
    )

    api.routes.clear()
    api.on("GET", APP, make_app(state="deleting"), (404, {"detail": "app not found"}))
    assert (
        wait.wait_for_state(client(), make_app(), target="deleted", timeout=60, progress=False)[
            "state"
        ]
        == "deleted"
    )


def test_wait_for_state_fails_on_failed_state(api):
    api.on("GET", APP, make_app(state="deploy_failed"))
    api.on("GET", f"{APP}/builds/build000001/logs", "log")
    with pytest.raises(CliError) as e:
        wait.wait_for_state(client(), make_app(), target="running", timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED


def test_wait_for_state_propagates_other_errors(api):
    api.on("GET", APP, (403, {"detail": "forbidden"}))
    with pytest.raises(CliError) as e:
        wait.wait_for_state(client(), make_app(), target="deleted", timeout=60, progress=False)
    assert e.value.code == ExitCode.AUTH


def scan(sid, status, **counts):
    return {
        "id": sid,
        "status": status,
        "error": None,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "unknown_count": 0,
        **counts,
    }


def test_wait_for_scan(api):
    api.on(
        "GET",
        f"{APP}/scans",
        [scan("s1", "succeeded")],
        [scan("s2", "running")],
        [scan("s2", "succeeded", high_count=2)],
    )
    result = wait.wait_for_scan(
        client(), make_app(), previous_scan_id="s1", timeout=60, progress=False
    )
    assert result["id"] == "s2" and result["high_count"] == 2


def test_wait_for_scan_failure(api):
    api.on("GET", f"{APP}/scans", [{**scan("s2", "failed"), "error": "trivy crashed"}])
    with pytest.raises(CliError) as e:
        wait.wait_for_scan(client(), make_app(), previous_scan_id=None, timeout=60, progress=False)
    assert e.value.code == ExitCode.FAILED
    assert "trivy crashed" in e.value.message


def test_follow_survives_log_fetch_errors(api, capsys):
    api.on(
        "GET",
        APP,
        make_app(state="building", current_build_id="b2"),
        make_app(state="building", current_build_id="b2"),
        make_app(state="running", current_build_id="b2"),
    )
    api.on(
        "GET", f"{APP}/builds/b2/logs", (500, {"detail": "boom"}), (500, {"detail": "boom"}), "ok\n"
    )
    result = wait.wait_for_rollout(client(), make_app(), timeout=60, follow=True, progress=False)
    assert result["state"] == "running"
    err = capsys.readouterr().err
    assert err.count("build log unavailable") == 1 and "ok" in err
