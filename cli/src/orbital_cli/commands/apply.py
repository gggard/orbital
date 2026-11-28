"""`orbital apply -f orbital.toml`: create or update an app declaratively."""

from __future__ import annotations

from pathlib import Path

import typer

from .. import manifest
from .. import wait as waiting
from ..output import emit, emit_json, info
from ..resolve import find_app
from ..state import get_state
from .apps import show_app
from .common import timeout_option


def apply(
    file: Path = typer.Option(
        Path("orbital.toml"), "-f", "--file", help="Manifest to apply", show_default=True
    ),
    redeploy: bool = typer.Option(
        True,
        "--redeploy/--no-redeploy",
        help="Redeploy after applying, even if no setting needs a rebuild",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan and change nothing"),
    wait: bool = typer.Option(
        False, "--wait", help="Block until the resulting deploy succeeds (exit 0) or fails (exit 8)"
    ),
    follow: bool = typer.Option(
        False, "--follow", help="Stream build logs to stderr while waiting (implies --wait)"
    ),
    timeout: float = timeout_option(),
) -> None:
    """Create the app described by the manifest, or update the settings that
    differ and redeploy. Secrets are never read from the manifest."""
    s = get_state()
    spec = manifest.load(file)
    app = find_app(s.client, spec["slug"])
    plan = manifest.plan(spec, app, redeploy=redeploy)

    if dry_run:
        if s.fmt == "json":
            emit_json(plan.to_dict())
        else:
            print(plan.describe())
        return
    if not s.quiet:
        info(plan.describe())

    if plan.action == "create":
        result = s.client.post("/apps", json=spec)
        before = {**result, "current_build_id": None}
    else:
        assert app is not None
        before = app
        result = app
        if plan.action == "update":
            payload = {k: c["to"] for k, c in plan.changes.items()}
            result = s.client.patch(f"/apps/{app['id']}", json=payload)
        if plan.redeploy and not plan.rebuild_by_patch:
            s.client.post(f"/apps/{app['id']}/deploy")

    building_already = "already in progress" in plan.reason
    if (wait or follow) and (plan.redeploy or building_already):
        if building_already:
            # follow the build that's already running rather than a new one
            result = waiting.wait_for_state(
                s.client, before, target="running", timeout=timeout, progress=not s.quiet
            )
        else:
            result = waiting.wait_for_rollout(
                s.client, before, timeout=timeout, follow=follow, progress=not s.quiet
            )
    elif plan.redeploy and not s.quiet:
        info(f"{spec['slug']}: deploy scheduled")
    if s.fmt == "name":
        print(result["slug"])
    elif s.fmt == "json":
        emit(result, "json")
    else:
        show_app(result)


def register(app: typer.Typer) -> None:
    app.command("apply")(apply)
