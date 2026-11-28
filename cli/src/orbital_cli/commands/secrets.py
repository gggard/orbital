"""`orbital secrets get|set`."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import typer

from ..errors import usage
from ..output import emit, info, write_text
from ..resolve import resolve_app
from ..state import get_state
from .common import APP_ARG

secrets_app = typer.Typer(
    help="Read or replace an app's secrets (mounted as .streamlit/secrets.toml).",
    no_args_is_help=True,
)


def read_secrets(path: Path) -> str:
    """Read and locally validate a secrets TOML file ('-' = stdin)."""
    if str(path) == "-":
        text = sys.stdin.read()
    else:
        try:
            text = path.read_text()
        except OSError as e:
            raise usage(f"cannot read {path}: {e.strerror}") from e
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        # don't echo the content: it's secret
        raise usage(f"secrets are not valid TOML: {e}") from e
    return text


@secrets_app.command("get")
def get_secrets(app: str = APP_ARG) -> None:
    """Print the secrets TOML to stdout (owners and admins only)."""
    s = get_state()
    target = resolve_app(s.client, app)
    write_text(s.client.get_text(f"/apps/{target['id']}/secrets"))


@secrets_app.command("set")
def set_secrets(
    app: str = APP_ARG,
    file: Path = typer.Option(
        ..., "-f", "--file", help="Secrets TOML file, or '-' for stdin", allow_dash=True
    ),
) -> None:
    """Replace the secrets. The app restarts without a rebuild."""
    s = get_state()
    target = resolve_app(s.client, app)
    text = read_secrets(file)
    result = s.client.put(f"/apps/{target['id']}/secrets", json={"secrets_toml": text})
    if s.fmt == "json":
        emit(result, "json")
    elif not s.quiet:
        info(f"{target['slug']}: {result.get('status', 'secrets updated')}")


def register(app: typer.Typer) -> None:
    app.add_typer(secrets_app, name="secrets")
