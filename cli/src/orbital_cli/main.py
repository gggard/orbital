"""`orbital` entry point: global options, error reporting, command tree."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer
from typer.core import TyperGroup

from . import __version__, config
from .errors import CliError, ExitCode
from .output import default_format
from .state import State, get_state, set_state

# Global options, accepted anywhere on the command line: people (and agents)
# write `orbital apps list -o json` as often as `orbital -o json apps list`.
_GLOBAL_WITH_VALUE = {"--url", "--profile", "--token", "-o", "--output"}
_GLOBAL_FLAGS = {"--token-stdin", "--no-input", "-q", "--quiet", "-v", "--verbose"}


def hoist_global_options(args: list[str]) -> list[str]:
    """Move global options that appear after the subcommand to the front,
    where Click expects them. Stops at `--`."""
    front: list[str] = []
    rest: list[str] = []
    subcommand: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            rest.extend(args[i:])
            break
        name = arg.split("=", 1)[0]
        if subcommand is None:
            if arg.startswith("-"):
                front.append(arg)
                if arg in _GLOBAL_WITH_VALUE and i + 1 < len(args):
                    front.append(args[i + 1])
                    i += 1
            else:
                subcommand = arg
                rest.append(arg)
        elif name in _GLOBAL_WITH_VALUE or (arg.startswith("-o") and len(arg) > 2):
            front.append(arg)
            if arg in _GLOBAL_WITH_VALUE and i + 1 < len(args):
                front.append(args[i + 1])
                i += 1
        elif arg in _GLOBAL_FLAGS and not (subcommand == "login" and arg == "--token-stdin"):
            front.append(arg)
        else:
            rest.append(arg)
        i += 1
    return front + rest


class OrbitalGroup(TyperGroup):
    """Root group: accepts global options anywhere, and turns CliError (from
    any subcommand) into a message on stderr and the documented exit code."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        return super().parse_args(ctx, hoist_global_options(list(args)))

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except CliError as e:
            report_error(e, ctx.obj)
            raise typer.Exit(int(e.code)) from None
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            raise typer.Exit(130) from None
        finally:
            set_state(None)


def report_error(error: CliError, state: Any = None) -> None:
    fmt = state.fmt if isinstance(state, State) else default_format(None)
    if fmt == "json":
        print(json.dumps(error.to_dict()), file=sys.stderr)
    else:
        print(f"error: {error.message}", file=sys.stderr)


app = typer.Typer(
    name="orbital",
    cls=OrbitalGroup,
    help="Deploy and manage Orbital apps from a terminal, CI pipeline or agent.",
    epilog="Docs: https://gggard.github.io/orbital/CLI/",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,  # never dump locals (tokens) in CI logs
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode=None,
)

# commands that may run against a profile that doesn't exist yet
_CREATES_PROFILE = {"login"}


def _print_version(value: bool) -> None:
    if value:
        print(f"orbital-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    url: str | None = typer.Option(
        None,
        "--url",
        metavar="URL",
        help="Control-plane base URL [env: ORBITAL_URL]",
        show_default=False,
    ),
    profile: str | None = typer.Option(
        None, "--profile", metavar="NAME", help="Config profile to use [env: ORBITAL_PROFILE]"
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        metavar="TOKEN",
        help="API token. Discouraged: visible in shell history and process lists; "
        "prefer ORBITAL_TOKEN or --token-stdin",
    ),
    token_stdin: bool = typer.Option(False, "--token-stdin", help="Read the API token from stdin"),
    output: str | None = typer.Option(
        None,
        "-o",
        "--output",
        metavar="FORMAT",
        help="Output format: table, json or name "
        "[default: table on a terminal, json otherwise] [env: ORBITAL_OUTPUT]",
        show_default=False,
    ),
    no_input: bool = typer.Option(False, "--no-input", help="Never prompt; fail instead"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Suppress progress messages"),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Log HTTP requests to stderr (tokens never shown)"
    ),
    _version: bool = typer.Option(
        False,
        "--version",
        help="Print the CLI version and exit",
        is_eager=True,
        callback=_print_version,
    ),
) -> None:
    try:
        if token_stdin:
            if ctx.invoked_subcommand == "login":
                raise CliError(
                    "use `orbital login --token-stdin` instead of the global flag", ExitCode.USAGE
                )
            token = sys.stdin.readline().strip() or None
        settings = config.resolve(
            url=url,
            token=token,
            profile=profile,
            output=output,
            strict_profile=ctx.invoked_subcommand not in _CREATES_PROFILE,
        )
    except CliError as e:
        report_error(e)
        raise typer.Exit(int(e.code)) from None
    state = State(settings=settings, verbose=verbose, quiet=quiet, no_input=no_input)
    ctx.obj = state
    set_state(state)


def _register() -> None:
    from .commands import admin, apply, apps, auth, misc, observe, secrets, tokens

    for module in (auth, apps, observe, secrets, apply, tokens, admin, misc):
        module.register(app)


_register()


def run() -> None:
    """Console-script entry point."""
    from typer.completion import completion_init

    completion_init()  # lets `eval "$(orbital completion bash)"` scripts call back in
    app()


__all__ = ["app", "run", "get_state", "__version__", "ExitCode"]
