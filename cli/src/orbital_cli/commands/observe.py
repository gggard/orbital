"""Logs, builds, metrics, analytics and vulnerability scans."""

from __future__ import annotations

import sys
from enum import StrEnum

import typer

from .. import wait as waiting
from ..errors import CliError, ExitCode
from ..output import Column, ago, col, emit, info, write_text
from ..resolve import resolve_app
from ..state import get_state
from .common import APP_ARG, timeout_option

builds_app = typer.Typer(help="Build history and build logs.", no_args_is_help=True)
scans_app = typer.Typer(help="Vulnerability scans of deployed images.", no_args_is_help=True)


# -- logs ------------------------------------------------------------------------


def logs(
    app: str = APP_ARG,
    follow: bool = typer.Option(False, "-f", "--follow", help="Stream new lines as they arrive"),
    tail: int = typer.Option(500, "--tail", min=1, help="Number of recent lines"),
) -> None:
    """Print the app's runtime logs (always raw text)."""
    s = get_state()
    target = resolve_app(s.client, app)
    path = f"/apps/{target['id']}/logs"
    if follow:
        for chunk in s.client.stream_text(path, follow="true", tail=tail):
            write_chunk(chunk)
    else:
        write_text(s.client.get_text(path, tail=tail))


def write_chunk(chunk: str) -> None:
    sys.stdout.write(chunk)
    sys.stdout.flush()


# -- builds ----------------------------------------------------------------------

BUILD_COLUMNS = [
    col("ID", "id"),
    col("PHASE", "phase"),
    Column("COMMIT", lambda b: (b.get("commit_sha") or "")[:10] or None),
    Column("STARTED", lambda b: ago(b.get("created_at"))),
    Column("FINISHED", lambda b: ago(b.get("finished_at")) if b.get("finished_at") else None),
    Column("ERROR", lambda b: b["error"].splitlines()[0][:60] if b.get("error") else None),
]


@builds_app.command("list")
def builds_list(app: str = APP_ARG) -> None:
    """Build history, newest first."""
    s = get_state()
    target = resolve_app(s.client, app)
    builds = list(reversed(s.client.get(f"/apps/{target['id']}/builds")))
    emit(builds, s.fmt, columns=BUILD_COLUMNS, empty="No builds yet.")


@builds_app.command("logs")
def builds_logs(
    app: str = APP_ARG,
    build: str | None = typer.Argument(None, help="Build id [default: the latest build]"),
    follow: bool = typer.Option(
        False, "-f", "--follow", help="Keep printing new lines until the build finishes"
    ),
    timeout: float = timeout_option("30m"),
) -> None:
    """Print a build's log (always raw text)."""
    s = get_state()
    target = resolve_app(s.client, app)
    builds = s.client.get(f"/apps/{target['id']}/builds")
    if build is None:
        if not builds:
            raise CliError(f"app {target['slug']} has no builds yet", ExitCode.NOT_FOUND)
        build = builds[-1]["id"]
    if not follow:
        write_text(s.client.get_text(f"/apps/{target['id']}/builds/{build}/logs"))
        return
    follower = waiting.BuildLogFollower(s.client, target["id"], build_id=build)
    poller = waiting.Poller(timeout, f"build {build} to finish", maximum=2.0)
    while True:
        follower.update(build)
        phase = next(
            (b["phase"] for b in s.client.get(f"/apps/{target['id']}/builds") if b["id"] == build),
            None,
        )
        if phase not in ("pending", "running"):
            follower.update(build)  # flush the final lines
            if phase == "failed":
                raise CliError(f"build {build} failed", ExitCode.FAILED)
            return
        poller.tick()


# -- metrics / analytics ------------------------------------------------------------


def _cores(v: float | None) -> str:
    return "-" if v is None else f"{v:.3f} cores"


def _mib(v: float | None) -> str:
    return "-" if v is None else f"{v / 1024 / 1024:.0f} MiB"


def metrics(app: str = APP_ARG) -> None:
    """Current CPU and memory against the app's limits, and restarts."""
    s = get_state()
    target = resolve_app(s.client, app)
    data = s.client.get(f"/apps/{target['id']}/metrics")
    if s.fmt != "table":
        emit(data, s.fmt)
        return
    if not data.get("available"):
        info("No metrics yet (the cluster's metrics-server has no data for this app).")
    cur, lim, rst = data.get("current") or {}, data.get("limits") or {}, data.get("restarts") or {}
    emit(
        data,
        "table",
        fields=[
            ("cpu", lambda _: f"{_cores(cur.get('cpu'))} / {_cores(lim.get('cpu'))}"),
            ("memory", lambda _: f"{_mib(cur.get('mem'))} / {_mib(lim.get('mem'))}"),
            ("restarts", lambda _: rst.get("count")),
            (
                "last restart",
                lambda _: (
                    f"{rst.get('last_reason')} ({ago(rst.get('last_at'))})"
                    if rst.get("last_at")
                    else None
                ),
            ),
        ],
    )


def analytics(app: str = APP_ARG) -> None:
    """Views and unique viewers."""
    s = get_state()
    target = resolve_app(s.client, app)
    data = s.client.get(f"/apps/{target['id']}/analytics")
    emit(
        data,
        s.fmt,
        fields=[
            ("total views", "total_views"),
            ("unique viewers 1d", "unique_viewers_1d"),
            ("unique viewers 7d", "unique_viewers_7d"),
            ("unique viewers 30d", "unique_viewers_30d"),
            ("last viewed", lambda d: ago(d.get("last_viewed_at"))),
        ],
    )


# -- scans -------------------------------------------------------------------------


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


SEVERITY_ORDER = ["critical", "high", "medium", "low", "unknown"]


def findings_at_or_above(scan: dict, threshold: str) -> int:
    levels = SEVERITY_ORDER[: SEVERITY_ORDER.index(threshold) + 1]
    return sum(int(scan.get(f"{level}_count") or 0) for level in levels)


SCAN_COLUMNS = [
    col("ID", "id"),
    col("STATUS", "status"),
    col("CRITICAL", "critical_count"),
    col("HIGH", "high_count"),
    col("MEDIUM", "medium_count"),
    col("LOW", "low_count"),
    Column("STARTED", lambda r: ago(r.get("created_at"))),
    col("BUILD", "build_id"),
]

VULN_COLUMNS = [
    col("SEVERITY", "severity"),
    col("ID", "vuln_id"),
    col("PACKAGE", "pkg_name"),
    col("INSTALLED", "installed_version"),
    col("FIXED", "fixed_version"),
    Column("TITLE", lambda v: (v.get("title") or "")[:60] or None),
]


@scans_app.command("list")
def scans_list(app: str = APP_ARG) -> None:
    """Scan history, newest first."""
    s = get_state()
    target = resolve_app(s.client, app)
    emit(
        s.client.get(f"/apps/{target['id']}/scans"),
        s.fmt,
        columns=SCAN_COLUMNS,
        empty="No scans yet.",
    )


@scans_app.command("show")
def scans_show(
    app: str = APP_ARG,
    scan: str | None = typer.Argument(None, help="Scan id [default: the latest scan]"),
    severity: Severity | None = typer.Option(
        None, "--severity", help="Only findings at or above this severity"
    ),
) -> None:
    """List the vulnerabilities found by a scan."""
    s = get_state()
    target = resolve_app(s.client, app)
    if scan is None:
        scans = s.client.get(f"/apps/{target['id']}/scans")
        if not scans:
            raise CliError(f"app {target['slug']} has no scans yet", ExitCode.NOT_FOUND)
        scan = scans[0]["id"]
    vulns = s.client.get(f"/apps/{target['id']}/scans/{scan}/vulnerabilities")
    if severity is not None:
        allowed = set(SEVERITY_ORDER[: SEVERITY_ORDER.index(severity.value) + 1])
        vulns = [v for v in vulns if v.get("severity") in allowed]
    vulns.sort(key=lambda v: SEVERITY_ORDER.index(v.get("severity", "unknown")))
    emit(vulns, s.fmt, columns=VULN_COLUMNS, name_key="vuln_id", empty="No vulnerabilities found.")


@scans_app.command("run")
def scans_run(
    app: str = APP_ARG,
    wait: bool = typer.Option(False, "--wait", help="Block until the scan finishes"),
    fail_on: Severity | None = typer.Option(
        None,
        "--fail-on",
        help="Exit 8 if the scan finds anything at or above this severity (implies --wait)",
    ),
    timeout: float = timeout_option("15m"),
) -> None:
    """Request a vulnerability scan of the app's current image."""
    s = get_state()
    target = resolve_app(s.client, app)
    scans = s.client.get(f"/apps/{target['id']}/scans")
    previous = scans[0]["id"] if scans else None
    result = s.client.post(f"/apps/{target['id']}/scan")
    if not s.quiet:
        info(f"{target['slug']}: {result.get('status', 'scan scheduled')}")
    if not (wait or fail_on):
        if s.fmt == "json":
            emit(result, "json")
        return
    finished = waiting.wait_for_scan(
        s.client, target, previous_scan_id=previous, timeout=timeout, progress=not s.quiet
    )
    emit(finished, s.fmt, fields=[(c.header.lower(), c.get) for c in SCAN_COLUMNS])
    if fail_on is not None:
        found = findings_at_or_above(finished, fail_on.value)
        if found:
            raise CliError(
                f"scan found {found} vulnerabilit{'y' if found == 1 else 'ies'} "
                f"at or above {fail_on.value}",
                ExitCode.FAILED,
            )


def register(app: typer.Typer) -> None:
    app.command("logs")(logs)
    app.add_typer(builds_app, name="builds")
    app.command("metrics")(metrics)
    app.command("analytics")(analytics)
    app.add_typer(scans_app, name="scans")
