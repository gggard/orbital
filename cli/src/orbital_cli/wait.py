"""Blocking until an asynchronous operation settles (`--wait`).

The control plane answers deploy/reboot/wake/delete with 202 and a
reconciler does the work on its next tick, so waiting means polling
`GET /apps/{id}` with backoff:

1. While `pending_action` is set, the reconciler hasn't picked the request
   up yet: keep waiting. (Servers that predate the field fall back to
   comparing `current_build_id`/`updated_at` with a pre-request snapshot.)
2. A deploy has started once `current_build_id` differs from the snapshot;
   it succeeded when the app is `running` on that build, and failed on
   `build_failed`/`deploy_failed`.
3. If the reconciler cleared the request without starting a build and the
   app is `build_failed`, the build never started (e.g. the branch could not
   be resolved).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .client import Client
from .errors import CliError, ExitCode
from .output import info

FAILED_STATES = frozenset({"build_failed", "deploy_failed"})
FAILURE_LOG_LINES = 50
_NO_LOGS = "[no logs available]"

# indirection so tests can run the loops without real time passing
sleep: Callable[[float], None] = time.sleep
monotonic: Callable[[], float] = time.monotonic


class Poller:
    """Backoff from 1s to 5s; raises exit code 7 at the deadline."""

    def __init__(self, timeout: float, what: str, *, initial: float = 1.0, maximum: float = 5.0):
        self.deadline = monotonic() + timeout
        self.timeout = timeout
        self.what = what
        self.interval = initial
        self.maximum = maximum

    def tick(self) -> None:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise CliError(
                f"timed out after {_fmt_duration(self.timeout)} waiting for {self.what}; "
                "the operation continues server-side",
                ExitCode.TIMEOUT,
            )
        sleep(min(self.interval, remaining))
        self.interval = min(self.interval * 1.5, self.maximum)


def _fmt_duration(seconds: float) -> str:
    if seconds >= 60 and seconds % 60 == 0:
        return f"{int(seconds // 60)}m"
    return f"{seconds:g}s"


def new_lines(previous: list[str], current: list[str]) -> list[str]:
    """Lines of `current` not yet printed, when both are tails of one growing
    log: the longest suffix of `previous` that prefixes `current` overlaps."""
    if not previous:
        return current
    for k in range(min(len(previous), len(current)), 0, -1):
        if previous[-k:] == current[:k]:
            return current[k:]
    return current


@dataclass
class BuildLogFollower:
    """Streams a build's log to stderr by polling (the API has no
    build-log streaming yet), printing only lines not seen before."""

    client: Client
    app_id: str
    build_id: str | None = None
    printed: list[str] = field(default_factory=list)
    warned: bool = False

    def update(self, build_id: str) -> None:
        if build_id != self.build_id:
            self.build_id = build_id
            self.printed = []
            info(f"--- build {build_id} ---")
        try:
            text = self.client.get_text(f"/apps/{self.app_id}/builds/{build_id}/logs")
        except CliError as e:
            # log streaming is best effort: a hiccup fetching logs (the build
            # pod not scheduled yet, a 5xx) must not fail the wait itself
            if not self.warned:
                info(f"(build log unavailable for now: {e.message})")
                self.warned = True
            return
        lines = [] if text.strip() == _NO_LOGS else text.splitlines()
        for line in new_lines(self.printed, lines):
            info(line)
        if lines:
            self.printed = lines


def failure(client: Client, app: dict, *, logs_shown: bool) -> CliError:
    """Exit-8 error for a failed build/rollout, after printing the app's
    error and (unless they were already streamed) the build log tail."""
    build_id = app.get("current_build_id")
    if build_id and not logs_shown:
        try:
            text = client.get_text(f"/apps/{app['id']}/builds/{build_id}/logs")
        except CliError:
            text = ""
        tail = [line for line in text.splitlines() if line.strip() != _NO_LOGS]
        if tail:
            info(f"--- last {FAILURE_LOG_LINES} lines of build {build_id} ---")
            for line in tail[-FAILURE_LOG_LINES:]:
                info(line)
    detail = f": {app['error']}" if app.get("error") else ""
    return CliError(f"app {app['slug']} is {app['state']}{detail}", ExitCode.FAILED)


class _Progress:
    def __init__(self, slug: str, enabled: bool):
        self.slug = slug
        self.enabled = enabled
        self.last: str | None = None

    def report(self, app: dict) -> None:
        state = app["state"]
        pending = app.get("pending_action")
        label = f"{state} ({pending} pending)" if pending and pending != "none" else state
        if self.enabled and label != self.last:
            info(f"{self.slug}: {label}")
        self.last = label


def _pending(app: dict, action: str) -> bool:
    return app.get("pending_action") == action


def wait_for_rollout(
    client: Client,
    before: dict,
    *,
    timeout: float,
    follow: bool = False,
    progress: bool = True,
) -> dict:
    """Wait for the build+rollout requested after the `before` snapshot."""
    app_id, slug = before["id"], before["slug"]
    previous_build = before.get("current_build_id")
    supports_pending = "pending_action" in before
    poller = Poller(timeout, f"{slug} to deploy")
    reporter = _Progress(slug, progress)
    follower = BuildLogFollower(client, app_id) if follow else None
    while True:
        app = client.get(f"/apps/{app_id}")
        reporter.report(app)
        state, build = app["state"], app.get("current_build_id")
        started = build is not None and build != previous_build
        if follower is not None and started:
            follower.update(build)
        if started and not _pending(app, "deploy"):
            if state == "running":
                return app
            if state in FAILED_STATES:
                raise failure(client, app, logs_shown=follower is not None)
        elif not started and state == "build_failed":
            # cleared without starting a build: the build never started
            never_started = (
                not _pending(app, "deploy")
                if supports_pending
                else app.get("updated_at") != before.get("updated_at")
            )
            if never_started:
                raise failure(client, app, logs_shown=False)
        poller.tick()


def wait_for_reboot(client: Client, before: dict, *, timeout: float, progress: bool = True) -> dict:
    app_id, slug = before["id"], before["slug"]
    poller = Poller(timeout, f"{slug} to restart")
    reporter = _Progress(slug, progress)
    left_running = False
    while True:
        app = client.get(f"/apps/{app_id}")
        reporter.report(app)
        state = app["state"]
        picked_up = not _pending(app, "reboot") if "pending_action" in app else left_running
        if state != "running":
            left_running = True
        if picked_up and state == "running":
            return app
        if picked_up and state in FAILED_STATES:
            raise failure(client, app, logs_shown=True)
        poller.tick()


def wait_for_state(
    client: Client,
    app: dict,
    *,
    target: str,
    timeout: float,
    progress: bool = True,
    fail_on_failed: bool = True,
) -> dict:
    """Wait until the app is in `target` state with nothing pending.
    `target="deleted"` waits for the app to disappear (404)."""
    app_id, slug = app["id"], app["slug"]
    poller = Poller(timeout, f"{slug} to be {target}")
    reporter = _Progress(slug, progress)
    while True:
        try:
            current = client.get(f"/apps/{app_id}")
        except CliError as e:
            if target == "deleted" and e.code == ExitCode.NOT_FOUND:
                if progress:
                    info(f"{slug}: deleted")
                return {**app, "state": "deleted"}
            raise
        reporter.report(current)
        settled = current.get("pending_action") in (None, "none")
        if target != "deleted" and settled:
            if current["state"] == target:
                return current
            if fail_on_failed and current["state"] in FAILED_STATES:
                raise failure(client, current, logs_shown=False)
        poller.tick()


def wait_for_scan(
    client: Client, app: dict, *, previous_scan_id: str | None, timeout: float, progress: bool
) -> dict:
    """Wait for a scan newer than `previous_scan_id` to finish; returns it."""
    poller = Poller(timeout, f"{app['slug']} scan to finish")
    last_status = None
    while True:
        scans = client.get(f"/apps/{app['id']}/scans")  # newest first
        latest = scans[0] if scans else None
        if latest is not None and latest["id"] != previous_scan_id:
            if progress and latest["status"] != last_status:
                info(f"{app['slug']}: scan {latest['status']}")
            last_status = latest["status"]
            if latest["status"] == "failed":
                raise CliError(
                    f"scan of {app['slug']} failed: {latest.get('error') or 'unknown error'}",
                    ExitCode.FAILED,
                )
            if latest["status"] not in ("pending", "running"):
                return latest
        poller.tick()
