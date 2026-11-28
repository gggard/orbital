"""`orbital admin ...` (admin role only)."""

from __future__ import annotations

import typer

from ..output import Column, ago, col, emit, info, write_text
from ..state import get_state
from .observe import SCAN_COLUMNS

admin_app = typer.Typer(help="Platform-wide views (admin role only).", no_args_is_help=True)


@admin_app.command("overview")
def overview() -> None:
    """Fleet summary: app count, running apps, resource usage per app."""
    s = get_state()
    data = s.client.get("/admin/overview")
    if s.fmt != "table":
        emit(data["apps"] if s.fmt == "name" else data, s.fmt, name_key="slug")
        return
    t = data["totals"]
    info(
        f"{t['app_count']} apps, {t['running_count']} running, "
        f"{t['cpu']:.2f} cores, {t['mem'] / 1024 / 1024:.0f} MiB in use"
    )
    emit(
        data["apps"],
        "table",
        columns=[
            col("SLUG", "slug"),
            col("STATE", "state"),
            Column("CPU", lambda a: None if a.get("cpu") is None else f"{a['cpu']:.3f}"),
            Column(
                "MEM MIB", lambda a: None if a.get("mem") is None else f"{a['mem'] / 2**20:.0f}"
            ),
            col("RESTARTS", "restarts"),
            col("OWNERS", "owner_groups"),
        ],
        empty="No apps.",
    )


@admin_app.command("activity")
def activity(
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="Number of events"),
) -> None:
    """Recent platform-wide events, newest first."""
    s = get_state()
    emit(
        s.client.get("/admin/activity", limit=limit),
        s.fmt,
        columns=[
            Column("WHEN", lambda e: ago(e.get("created_at"))),
            col("LEVEL", "level"),
            col("APP", "slug"),
            col("EVENT", "text"),
            col("ACTOR", "actor"),
        ],
        empty="No activity.",
    )


@admin_app.command("logs")
def logs(tail: int = typer.Option(500, "--tail", min=1, help="Number of recent lines")) -> None:
    """Control-plane logs (always raw text)."""
    write_text(get_state().client.get_text("/admin/logs", tail=tail))


@admin_app.command("scans")
def scans() -> None:
    """Latest vulnerability scan of every app."""
    s = get_state()
    emit(
        s.client.get("/admin/scans"),
        s.fmt,
        columns=[col("APP", "slug"), *SCAN_COLUMNS],
        name_key="slug",
        empty="No scans.",
    )


def register(app: typer.Typer) -> None:
    app.add_typer(admin_app, name="admin")
