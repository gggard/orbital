"""Configuration: flags > environment variables > config file profiles.

The config file is TOML at $ORBITAL_CONFIG, else
$XDG_CONFIG_HOME/orbital/config.toml, else ~/.config/orbital/config.toml:

    default_profile = "prod"

    [profiles.prod]
    url = "https://orbital.example.com"
    token = "orbpat_..."
    output = "json"        # optional
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import usage

DEFAULT_URL = "http://localhost:8000"
DEFAULT_PROFILE = "default"
OUTPUT_FORMATS = ("table", "json", "name")


def config_path(env: Mapping[str, str] = os.environ) -> Path:
    if env.get("ORBITAL_CONFIG"):
        return Path(env["ORBITAL_CONFIG"])
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "orbital" / "config.toml"


def load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    _warn_if_world_readable(path)
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise usage(f"invalid config file {path}: {e}") from e


def _warn_if_world_readable(path: Path) -> None:
    if os.name != "posix":
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"warning: {path} is accessible by other users and may contain API tokens; "
            f"run: chmod 600 {path}",
            file=sys.stderr,
        )


@dataclass
class Settings:
    url: str
    token: str | None
    profile: str
    output: str | None  # None: pick by whether stdout is a TTY
    config_file: Path


def resolve(
    *,
    url: str | None = None,
    token: str | None = None,
    profile: str | None = None,
    output: str | None = None,
    env: Mapping[str, str] = os.environ,
    strict_profile: bool = True,
) -> Settings:
    path = config_path(env)
    data = load_file(path)
    profile_name = (
        profile or env.get("ORBITAL_PROFILE") or data.get("default_profile") or DEFAULT_PROFILE
    )
    profiles = data.get("profiles", {})
    explicit = profile or env.get("ORBITAL_PROFILE")
    if strict_profile and explicit and profile_name not in profiles:
        # an explicitly requested profile that doesn't exist is a typo, not a fallback
        raise usage(f"profile {profile_name!r} not found in {path}")
    p = profiles.get(profile_name, {})

    out = output or env.get("ORBITAL_OUTPUT") or p.get("output")
    if out is not None and out not in OUTPUT_FORMATS:
        raise usage(f"invalid output format {out!r} (choose from {', '.join(OUTPUT_FORMATS)})")

    return Settings(
        url=(url or env.get("ORBITAL_URL") or p.get("url") or DEFAULT_URL).rstrip("/"),
        token=token or env.get("ORBITAL_TOKEN") or p.get("token") or None,
        profile=profile_name,
        output=out,
        config_file=path,
    )


# -- writing -----------------------------------------------------------------


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        # JSON string escapes are a subset of TOML basic-string escapes
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"unsupported config value {value!r}")


def _key(k: str) -> str:
    return k if k.replace("-", "").replace("_", "").isalnum() else json.dumps(k)


def dumps(data: dict[str, Any]) -> str:
    """Serialize the config structure (scalars + one level of named tables
    under [profiles]); tomllib can read but not write TOML."""
    lines = [f"{_key(k)} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        for name, table in v.items():
            lines.append("")
            lines.append(f"[{_key(k)}.{_key(name)}]")
            lines.extend(f"{_key(tk)} = {_toml_value(tv)}" for tk, tv in table.items())
    return "\n".join(lines).lstrip("\n") + "\n"


def write_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # create with 0600 up front so the token is never briefly world-readable
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(dumps(data))
    os.chmod(path, 0o600)


def save_profile(path: Path, name: str, *, url: str, token: str | None) -> None:
    data = load_file(path)
    profiles = data.setdefault("profiles", {})
    entry = profiles.setdefault(name, {})
    entry["url"] = url
    if token:
        entry["token"] = token
    else:
        entry.pop("token", None)
    data.setdefault("default_profile", name)
    write_file(path, data)


def remove_token(path: Path, name: str) -> bool:
    data = load_file(path)
    entry = data.get("profiles", {}).get(name)
    if not entry or "token" not in entry:
        return False
    del entry["token"]
    write_file(path, data)
    return True
