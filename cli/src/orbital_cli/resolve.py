"""Turn an APP argument (slug or id) into the app object."""

from __future__ import annotations

from .client import Client
from .errors import CliError, ExitCode


def find_app(client: Client, ref: str) -> dict | None:
    """The visible app whose slug or id is `ref`, or None.

    One `GET /apps` covers both: slugs and ids are each unique, and the list
    holds exactly the apps `GET /apps/{id}` would let us see.
    """
    apps = client.get("/apps")
    for app in apps:
        if app["slug"] == ref:
            return app
    for app in apps:
        if app["id"] == ref:
            return app
    return None


def resolve_app(client: Client, ref: str) -> dict:
    app = find_app(client, ref)
    if app is None:
        raise CliError(f"app {ref!r} not found", ExitCode.NOT_FOUND, http_status=404)
    return app
