"""Options and helpers shared by several command modules."""

from __future__ import annotations

import typer

from ..state import parse_duration

DEFAULT_TIMEOUT = "15m"

APP_ARG = typer.Argument(..., metavar="APP", help="App slug or id")


def timeout_option(default: str = DEFAULT_TIMEOUT) -> float:
    return typer.Option(
        default,
        "--timeout",
        help="Give up waiting after this long (90s, 10m, 1h); exit code 7",
        parser=parse_duration,
        metavar="DURATION",
    )


def wait_option(what: str = "the operation") -> bool:
    return typer.Option(
        False, "--wait", help=f"Block until {what} succeeds (exit 0) or fails (exit 8)"
    )


def yes_option() -> bool:
    return typer.Option(
        False, "-y", "--yes", help="Skip the confirmation (required when non-interactive)"
    )


APP_COLUMNS_KEYS = ("slug", "app_type", "state", "url", "updated_at")
