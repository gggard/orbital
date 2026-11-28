"""`orbital.toml`: a declarative app definition committed next to the code.

    slug = "sales-dashboard"
    repo_url = "https://github.com/acme/sales-dashboard"
    branch = "main"
    app_type = "streamlit"
    main_file = "app.py"
    public = false
    allowed_groups = ["sales"]

    [hibernate]
    enabled = true
    after_seconds = 3600

    [poll]
    enabled = false
    interval_seconds = 300

Field names and rules follow the API's AppCreate body. Secrets are
deliberately not accepted: the manifest is committed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import usage

_STR = (
    "slug",
    "repo_url",
    "branch",
    "app_type",
    "main_file",
    "python_version",
    "build_command",
    "output_dir",
)
_BOOL = ("public",)
_LIST = ("allowed_groups", "owner_groups", "tags")
_TABLES = {
    "hibernate": {
        "enabled": ("hibernate_enabled", bool),
        "after_seconds": ("hibernate_after_seconds", int),
    },
    "poll": {"enabled": ("poll_enabled", bool), "interval_seconds": ("poll_interval_seconds", int)},
}
APP_TYPES = ("streamlit", "static")
STREAMLIT_ONLY = ("main_file", "python_version")
STATIC_ONLY = ("build_command", "output_dir")
IMMUTABLE = ("repo_url", "app_type")  # can't be PATCHed; slug is the identity
REBUILD_FIELDS = ("branch", "main_file", "python_version", "build_command", "output_dir")
SET_FIELDS = ("allowed_groups", "owner_groups")  # order doesn't matter
CASE_INSENSITIVE_SET_FIELDS = ("tags",)  # the server dedupes tags case-insensitively


def parse(text: str, source: str = "orbital.toml") -> dict[str, Any]:
    """Parse and validate a manifest into an AppCreate-shaped dict."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise usage(f"{source}: invalid TOML: {e}") from e

    spec: dict[str, Any] = {}
    for key, value in raw.items():
        if key in ("secrets", "secrets_toml"):
            raise usage(
                f"{source}: secrets don't belong in a committed manifest; "
                "use `orbital secrets set APP -f -` from your CI secret store"
            )
        if key in _TABLES:
            if not isinstance(value, dict):
                raise usage(f"{source}: [{key}] must be a table")
            for sub, sub_value in value.items():
                if sub not in _TABLES[key]:
                    allowed = ", ".join(_TABLES[key])
                    raise usage(f"{source}: unknown key {key}.{sub} (allowed: {allowed})")
                api_name, typ = _TABLES[key][sub]
                spec[api_name] = _check(f"{key}.{sub}", sub_value, typ, source)
        elif key in _STR:
            spec[key] = _check(key, value, str, source)
        elif key in _BOOL:
            spec[key] = _check(key, value, bool, source)
        elif key in _LIST:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise usage(f"{source}: {key} must be a list of strings")
            spec[key] = value
        else:
            raise usage(f"{source}: unknown key {key!r}")

    for required in ("slug", "repo_url"):
        if required not in spec:
            raise usage(f"{source}: missing required key {required!r}")
    app_type = spec.setdefault("app_type", "streamlit")
    if app_type not in APP_TYPES:
        raise usage(f"{source}: app_type must be one of {', '.join(APP_TYPES)}")
    wrong = STATIC_ONLY if app_type == "streamlit" else STREAMLIT_ONLY
    for key in wrong:
        if key in spec:
            raise usage(f"{source}: {key} does not apply to {app_type} apps")
    for key in ("hibernate_after_seconds", "poll_interval_seconds"):
        if key in spec and spec[key] <= 0:
            raise usage(f"{source}: {key.replace('_', '.', 1)} must be positive")
    return spec


def _check(name: str, value: Any, typ: type, source: str) -> Any:
    # bool is an int subclass: reject `after_seconds = true`
    if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
        raise usage(f"{source}: {name} must be a {typ.__name__}")
    return value


def load(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text()
    except OSError as e:
        raise usage(f"cannot read {path}: {e.strerror}") from e
    return parse(text, str(path))


def _norm(key: str, value: Any) -> Any:
    if key in SET_FIELDS and isinstance(value, list):
        return sorted(set(value))
    if key in CASE_INSENSITIVE_SET_FIELDS and isinstance(value, list):
        return sorted({v.strip().lower() for v in value if v.strip()})
    return value


@dataclass
class Plan:
    action: str  # "create" | "update" | "none"
    slug: str
    changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    redeploy: bool = False
    reason: str = ""

    @property
    def rebuild_by_patch(self) -> bool:
        return any(k in REBUILD_FIELDS for k in self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "slug": self.slug,
            "changes": self.changes,
            "redeploy": self.redeploy,
            "reason": self.reason,
        }

    def describe(self) -> str:
        if self.action == "create":
            lines = [f"app {self.slug}: create"]
        elif self.action == "update":
            lines = [f"app {self.slug}: update"]
        else:
            lines = [f"app {self.slug}: settings up to date"]
        if self.action == "update":
            width = max(len(k) for k in self.changes)
            for key, change in self.changes.items():
                old, new = _show(change["from"]), _show(change["to"])
                lines.append(f"  {key.ljust(width)}  {old} -> {new}")
        elif self.action == "create":
            width = max(len(k) for k in self.changes)
            for key, change in self.changes.items():
                lines.append(f"  {key.ljust(width)}  {_show(change['to'])}")
        if self.redeploy:
            lines.append(f"  then: {self.reason}")
        elif self.reason:
            lines.append(f"  ({self.reason})")
        return "\n".join(lines)


def _show(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(f'"{v}"' for v in value) + "]"
    return str(value)


def plan(spec: dict[str, Any], app: dict | None, *, redeploy: bool) -> Plan:
    """Compare the manifest with the live app (None if it doesn't exist)."""
    slug = spec["slug"]
    if app is None:
        changes = {k: {"from": None, "to": v} for k, v in spec.items() if k != "slug"}
        return Plan("create", slug, changes, redeploy=True, reason="first build and deploy")

    for key in IMMUTABLE:
        if key in spec and spec[key] != app.get(key):
            raise usage(
                f"{key} of {slug} is {app.get(key)!r} but the manifest says {spec[key]!r}; "
                f"{key} can't change after creation (delete and recreate the app, "
                "or use a new slug)"
            )
    changes = {}
    for key, wanted in spec.items():
        if key in ("slug", *IMMUTABLE):
            continue
        current = app.get(key)
        if _norm(key, wanted) != _norm(key, current):
            changes[key] = {"from": current, "to": wanted}

    result = Plan("update" if changes else "none", slug, changes)
    branch = spec.get("branch", app.get("branch"))
    if result.rebuild_by_patch:
        result.redeploy, result.reason = True, f"rebuild (settings changed; branch {branch})"
    elif app.get("state") == "building" or app.get("pending_action") == "deploy":
        result.reason = "a build is already in progress; not starting another"
    elif redeploy:
        result.redeploy, result.reason = True, f"redeploy (branch {branch})"
    else:
        result.reason = "no redeploy (--no-redeploy)"
    return result
