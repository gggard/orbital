"""`orbital version`, `health`, `completion`."""

from __future__ import annotations

import contextlib
from enum import StrEnum

import typer

from .. import __version__
from ..errors import CliError, ExitCode
from ..output import emit
from ..state import get_state


class Shell(StrEnum):
    bash = "bash"
    zsh = "zsh"
    fish = "fish"


def version() -> None:
    """Print the CLI version and, if reachable, the platform version."""
    s = get_state()
    data: dict = {"cli": __version__, "platform": None, "url": s.settings.url}
    with contextlib.suppress(CliError):
        data["platform"] = s.client.get("/healthz").get("version")
    if s.fmt == "json":
        emit(data, "json")
        return
    print(f"orbital-cli {__version__}")
    print(f"platform    {data['platform'] or 'unreachable'} ({s.settings.url})")


def health() -> None:
    """Check the control plane's /healthz (exit 0 when healthy)."""
    s = get_state()
    data = s.client.get("/healthz")
    if data.get("status") != "ok":
        raise CliError(f"control plane unhealthy: {data}", ExitCode.ERROR)
    if s.fmt == "json":
        emit(data, "json")
    else:
        print(f"ok ({s.settings.url}, version {data.get('version')})")


def completion(shell: Shell = typer.Argument(..., help="Shell to generate the script for")) -> None:
    """Print a shell-completion script.

    \b
    bash:  eval "$(orbital completion bash)"      (add to ~/.bashrc)
    zsh:   eval "$(orbital completion zsh)"       (add to ~/.zshrc)
    fish:  orbital completion fish > ~/.config/fish/completions/orbital.fish
    """
    from typer.completion import get_completion_script

    print(
        get_completion_script(
            prog_name="orbital", complete_var="_ORBITAL_COMPLETE", shell=shell.value
        )
    )


def register(app: typer.Typer) -> None:
    app.command("version")(version)
    app.command("health")(health)
    app.command("completion")(completion)
