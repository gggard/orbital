"""`orbital tokens list|create|revoke` (your own personal API tokens)."""

from __future__ import annotations

import typer

from ..output import Column, ago, col, emit, info
from ..state import get_state
from .common import yes_option

tokens_app = typer.Typer(help="Manage your personal API tokens.", no_args_is_help=True)

TOKEN_COLUMNS = [
    col("ID", "id"),
    col("NAME", "name"),
    Column("CREATED", lambda t: ago(t.get("created_at"))),
    Column("EXPIRES", lambda t: (t.get("expires_at") or "")[:10] or None),
    Column("LAST USED", lambda t: ago(t.get("last_used_at")) if t.get("last_used_at") else None),
    Column("REVOKED", lambda t: ago(t.get("revoked_at")) if t.get("revoked_at") else None),
]


@tokens_app.command("list")
def list_tokens() -> None:
    """List your tokens (secret values are never shown)."""
    s = get_state()
    emit(s.client.get("/me/tokens"), s.fmt, columns=TOKEN_COLUMNS, empty="No tokens.")


@tokens_app.command("create")
def create_token(
    name: str = typer.Argument(..., help="A label, e.g. the pipeline that will use it"),
    ttl_days: int | None = typer.Option(
        None, "--ttl-days", min=1, help="Lifetime in days [default: the platform maximum]"
    ),
) -> None:
    """Create a token. Its secret is printed once and can't be retrieved again."""
    s = get_state()
    payload: dict = {"name": name}
    if ttl_days is not None:
        payload["ttl_days"] = ttl_days
    created = s.client.post("/me/tokens", json=payload)
    if s.fmt == "json":
        emit(created, "json")
        return
    print(created["token"])
    if not s.quiet:
        info(
            f"token {created['id']} ({name}) expires {created['expires_at'][:10]}; "
            "copy it now, it won't be shown again"
        )


@tokens_app.command("revoke")
def revoke_token(
    token_id: str = typer.Argument(..., metavar="ID", help="Token id (see `tokens list`)"),
    yes: bool = yes_option(),
) -> None:
    """Revoke a token, effective immediately."""
    s = get_state()
    s.confirm(f"Revoke token {token_id}?", yes)
    result = s.client.delete(f"/me/tokens/{token_id}")
    if s.fmt == "json":
        emit(result, "json")
    elif not s.quiet:
        info(f"token {token_id} revoked")


def register(app: typer.Typer) -> None:
    app.add_typer(tokens_app, name="tokens")
