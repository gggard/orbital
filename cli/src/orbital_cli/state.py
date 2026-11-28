"""Per-invocation state shared by all commands (stored on the Click context)."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

import typer

from .client import Client
from .config import Settings
from .errors import CliError, ExitCode, usage
from .output import default_format


@dataclass
class State:
    settings: Settings
    verbose: bool = False
    quiet: bool = False
    no_input: bool = False
    _client: Client | None = field(default=None, repr=False)

    @property
    def fmt(self) -> str:
        return default_format(self.settings.output)

    @property
    def interactive(self) -> bool:
        """Prompts, browsers and spinners only for a person at a terminal."""
        return not self.no_input and sys.stdin.isatty() and not os.environ.get("CI")

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client(self.settings.url, self.settings.token, verbose=self.verbose)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def confirm(self, prompt: str, yes: bool) -> None:
        """Gate a destructive action: --yes, or an interactive confirmation."""
        if yes:
            return
        if not self.interactive:
            raise usage("refusing to proceed without confirmation: pass --yes")
        if not typer.confirm(prompt, default=False, err=True):
            raise CliError("aborted", ExitCode.ERROR)


_current: State | None = None


def set_state(state: State | None) -> None:
    global _current
    if _current is not None and _current is not state:
        _current.close()
    _current = state


def get_state() -> State:
    """The state of the running invocation (set by the root callback)."""
    if _current is None:  # pragma: no cover - set by the root callback
        raise RuntimeError("CLI state not initialized")
    return _current


_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h)?\s*$")


def parse_duration(value: str) -> float:
    """'90s', '10m', '1h' or a bare number of seconds."""
    m = _DURATION.match(value)
    if not m:
        raise typer.BadParameter(f"invalid duration {value!r} (examples: 90s, 10m, 1h)")
    amount = float(m.group(1))
    return amount * {"s": 1, "m": 60, "h": 3600, None: 1}[m.group(2)]
