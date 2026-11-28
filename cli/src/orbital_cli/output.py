"""Rendering: `table` for people, `json` (the API response, unchanged) and
`name` (one identifier per line) for scripts.

Data goes to stdout; progress and diagnostics go to stderr via `info()`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def default_format(explicit: str | None) -> str:
    """An explicit choice wins; otherwise tables for terminals, JSON for
    pipes, files, CI log capture and agents."""
    if explicit:
        return explicit
    return "table" if stdout_is_tty() else "json"


@dataclass
class Column:
    header: str
    get: Callable[[dict], Any]


def col(header: str, key: str) -> Column:
    return Column(header, lambda row: row.get(key))


def ago(value: str | None) -> str:
    """Humanize an ISO timestamp from the API ("3m ago")."""
    if not value:
        return "-"
    try:
        then = datetime.fromisoformat(value)
    except ValueError:
        return value
    if then.tzinfo is None:  # the API serializes naive UTC datetimes
        then = then.replace(tzinfo=UTC)
    seconds = int((datetime.now(UTC) - then).total_seconds())
    if seconds < 0:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{seconds}s ago"


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ",".join(str(v) for v in value) or "-"
    return str(value)


def render_table(rows: Sequence[dict], columns: Sequence[Column]) -> str:
    cells = [[_cell(c.get(r)) for c in columns] for r in rows]
    headers = [c.header for c in columns]
    widths = [max(len(h), *(len(row[i]) for row in cells)) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)).rstrip()]
    lines.extend(
        "  ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)).rstrip() for row in cells
    )
    return "\n".join(lines)


def render_fields(obj: dict, fields: Sequence[tuple[str, Any]]) -> str:
    """Key/value block for a single object in table mode."""
    width = max(len(label) for label, _ in fields)
    out = []
    for label, value in fields:
        v = value(obj) if callable(value) else obj.get(value)
        out.append(f"{label.ljust(width)}  {_cell(v)}")
    return "\n".join(out)


def emit_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def emit(
    data: Any,
    fmt: str,
    *,
    columns: Sequence[Column] | None = None,
    fields: Sequence[tuple[str, Any]] | None = None,
    name_key: str = "id",
    empty: str = "No resources found.",
    text: Callable[[Any], str] | None = None,
) -> None:
    if fmt == "json":
        emit_json(data)
        return
    if fmt == "name":
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and name_key in item:
                print(item[name_key])
        return
    # table
    if text is not None:
        print(text(data))
    elif isinstance(data, list):
        if not data:
            info(empty)
            return
        print(render_table(data, columns or [Column(k.upper(), _getter(k)) for k in data[0]]))
    elif isinstance(data, dict) and fields is not None:
        print(render_fields(data, fields))
    elif isinstance(data, dict):
        print(render_fields(data, [(k, k) for k in data]))
    else:
        print(data)


def _getter(key: str) -> Callable[[dict], Any]:
    return lambda row: row.get(key)


def info(message: str) -> None:
    print(message, file=sys.stderr)


def write_text(text: str) -> None:
    """Raw text endpoints (logs, secrets): written as-is in every format."""
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
