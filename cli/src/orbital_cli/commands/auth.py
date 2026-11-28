"""`orbital login`, `logout`, `whoami`."""

from __future__ import annotations

import sys

import typer

from .. import config
from ..client import Client
from ..errors import CliError, ExitCode, usage
from ..output import emit, info
from ..state import get_state

WHOAMI_FIELDS = [
    ("email", "email"),
    ("role", "role"),
    ("groups", "groups"),
    ("can create", "can_create"),
    ("can publish", "can_publish"),
    ("auth enabled", "auth_enabled"),
]


def login(
    token_stdin: bool = typer.Option(
        False, "--token-stdin", help="Read the token from stdin instead of prompting"
    ),
) -> None:
    """Validate an API token and store it in the config file.

    Create a token in the console under "My tokens". Use --url and
    --profile to choose the platform and the profile name.
    """
    s = get_state()
    url = s.settings.url
    if token_stdin:
        token = sys.stdin.readline().strip()
    elif s.interactive:
        token = typer.prompt("API token (orbpat_...)", hide_input=True, err=True).strip()
    else:
        raise usage("no terminal to prompt on: pipe the token with --token-stdin")

    client = Client(url, token or None, verbose=s.verbose)
    try:
        me = client.get("/me")
    finally:
        client.close()
    if me.get("auth_enabled") and not token:
        raise CliError("a token is required: this platform has auth enabled", ExitCode.AUTH)

    config.save_profile(s.settings.config_file, s.settings.profile, url=url, token=token or None)
    if s.fmt == "json":
        emit({"profile": s.settings.profile, "url": url, **me}, "json")
        return
    if not me.get("auth_enabled"):
        info(f"{url} has auth disabled; saved profile {s.settings.profile!r} without a token")
    else:
        info(f"Logged in as {me['email']} ({me['role']}) on {url}")
    info(f"Saved to {s.settings.config_file} (profile {s.settings.profile!r})")


def logout() -> None:
    """Remove the stored token from the config file (does not revoke it:
    use `orbital tokens revoke` for that)."""
    s = get_state()
    removed = config.remove_token(s.settings.config_file, s.settings.profile)
    if removed:
        info(f"Removed the token of profile {s.settings.profile!r} from {s.settings.config_file}")
    else:
        info(f"No stored token for profile {s.settings.profile!r}")


def whoami() -> None:
    """Show the current identity, groups and role."""
    s = get_state()
    me = s.client.get("/me")
    emit(
        {"url": s.settings.url, "profile": s.settings.profile, **me} if s.fmt == "json" else me,
        s.fmt,
        fields=WHOAMI_FIELDS,
        name_key="email",
    )


def register(app: typer.Typer) -> None:
    app.command("login")(login)
    app.command("logout")(logout)
    app.command("whoami")(whoami)
