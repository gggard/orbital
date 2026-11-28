"""`orbital apps ...` and the top-level lifecycle verbs (deploy, reboot,
wake, wait, status)."""

from __future__ import annotations

import webbrowser
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer

from .. import wait as waiting
from ..errors import usage
from ..output import Column, ago, col, emit, info
from ..resolve import resolve_app
from ..state import get_state
from .common import APP_ARG, timeout_option, wait_option, yes_option

apps_app = typer.Typer(help="Create, inspect, update and delete apps.", no_args_is_help=True)


class AppType(StrEnum):
    streamlit = "streamlit"
    static = "static"


class WaitTarget(StrEnum):
    running = "running"
    deleted = "deleted"


APP_COLUMNS = [
    col("SLUG", "slug"),
    col("TYPE", "app_type"),
    col("STATE", "state"),
    col("URL", "url"),
    Column("UPDATED", lambda a: ago(a.get("updated_at"))),
]

APP_FIELDS: list[tuple[str, Any]] = [
    ("slug", "slug"),
    ("id", "id"),
    ("type", "app_type"),
    ("state", "state"),
    (
        "pending",
        lambda a: None if a.get("pending_action") in (None, "none") else a["pending_action"],
    ),
    ("error", "error"),
    ("url", "url"),
    ("repo", "repo_url"),
    ("branch", "branch"),
    ("main file", "main_file"),
    ("python", "python_version"),
    ("build command", "build_command"),
    ("output dir", "output_dir"),
    ("public", "public"),
    ("allowed groups", "allowed_groups"),
    ("owner groups", "owner_groups"),
    ("tags", "tags"),
    ("current build", "current_build_id"),
    (
        "hibernate",
        lambda a: (
            f"after {a['hibernate_after_seconds']}s"
            if a.get("hibernate_enabled") and a.get("hibernate_after_seconds")
            else a.get("hibernate_enabled")
        ),
    ),
    (
        "git poll",
        lambda a: (
            f"every {a['poll_interval_seconds']}s"
            if a.get("poll_enabled") and a.get("poll_interval_seconds")
            else a.get("poll_enabled")
        ),
    ),
    ("webhook", "webhook_path"),
    ("updated", lambda a: ago(a.get("updated_at"))),
]


def show_app(app: dict) -> None:
    emit(app, get_state().fmt, fields=APP_FIELDS, name_key="slug")


def _report(message: str) -> None:
    if not get_state().quiet:
        info(message)


# -- settings payload shared by create/update ---------------------------------


def settings_payload(
    *,
    branch: str | None,
    main_file: str | None,
    python_version: str | None,
    build_command: str | None,
    output_dir: str | None,
    public: bool | None,
    allowed_groups: list[str] | None,
    owner_groups: list[str] | None,
    tags: list[str] | None,
    hibernate: bool | None,
    hibernate_after_seconds: int | None,
    poll: bool | None,
    poll_interval_seconds: int | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "branch": branch,
        "main_file": main_file,
        "python_version": python_version,
        "build_command": build_command,
        "output_dir": output_dir,
        "public": public,
        # repeatable options: an empty list means "not given"
        "allowed_groups": allowed_groups or None,
        "owner_groups": owner_groups or None,
        "tags": tags or None,
        "hibernate_enabled": hibernate,
        "hibernate_after_seconds": hibernate_after_seconds,
        "poll_enabled": poll,
        "poll_interval_seconds": poll_interval_seconds,
    }
    return {k: v for k, v in payload.items() if v is not None}


BRANCH = typer.Option(None, "--branch", help="Git branch to track [create default: main]")
MAIN_FILE = typer.Option(None, "--main-file", help="Streamlit entry point")
PYTHON = typer.Option(None, "--python-version", help="Python version (streamlit)")
BUILD_COMMAND = typer.Option(None, "--build-command", help="npm build command (static)")
OUTPUT_DIR = typer.Option(None, "--output-dir", help="Directory served (static)")
PUBLIC = typer.Option(
    None, "--public/--private", help="Public, or behind login", show_default=False
)
ALLOWED = typer.Option(None, "--allowed-group", metavar="GROUP", help="Viewer group (repeatable)")
OWNERS = typer.Option(None, "--owner-group", metavar="GROUP", help="Owner group (repeatable)")
TAGS = typer.Option(None, "--tag", metavar="TAG", help="Tag (repeatable)")
HIBERNATE = typer.Option(None, "--hibernate/--no-hibernate", help="Scale to zero when idle")
HIBERNATE_AFTER = typer.Option(None, "--hibernate-after-seconds", min=1)
POLL = typer.Option(None, "--poll/--no-poll", help="Poll the branch for new commits")
POLL_INTERVAL = typer.Option(None, "--poll-interval-seconds", min=1)


# -- apps ---------------------------------------------------------------------


@apps_app.command("list")
def list_apps(
    tag: list[str] = typer.Option(None, "--tag", help="Only apps with this tag (repeatable)"),
    state: list[str] = typer.Option(None, "--state", help="Only apps in this state (repeatable)"),
) -> None:
    """List the apps you can see."""
    s = get_state()
    apps = s.client.get("/apps")
    if tag:
        wanted = {t.lower() for t in tag}
        apps = [a for a in apps if wanted & {t.lower() for t in a.get("tags", [])}]
    if state:
        apps = [a for a in apps if a["state"] in state]
    emit(apps, s.fmt, columns=APP_COLUMNS, name_key="slug", empty="No apps found.")


@apps_app.command("get")
def get_app(app: str = APP_ARG) -> None:
    """Show one app."""
    show_app(resolve_app(get_state().client, app))


@apps_app.command("create")
def create_app(
    slug: str = typer.Argument(..., help="DNS-safe name; the app is served at <slug>.<domain>"),
    repo: str = typer.Option(..., "--repo", help="Git repository URL"),
    app_type: AppType = typer.Option(AppType.streamlit, "--type", help="App type"),
    branch: str | None = BRANCH,
    main_file: str | None = MAIN_FILE,
    python_version: str | None = PYTHON,
    build_command: str | None = BUILD_COMMAND,
    output_dir: str | None = OUTPUT_DIR,
    public: bool | None = PUBLIC,
    allowed_group: list[str] = ALLOWED,
    owner_group: list[str] = OWNERS,
    tag: list[str] = TAGS,
    hibernate: bool | None = HIBERNATE,
    hibernate_after_seconds: int | None = HIBERNATE_AFTER,
    poll: bool | None = POLL,
    poll_interval_seconds: int | None = POLL_INTERVAL,
    secrets_file: Path | None = typer.Option(
        None,
        "--secrets-file",
        help="Secrets TOML to set at creation ('-' for stdin)",
        allow_dash=True,
    ),
    wait: bool = wait_option("the first deploy"),
    follow: bool = typer.Option(False, "--follow", help="Stream build logs while waiting"),
    timeout: float = timeout_option(),
) -> None:
    """Create an app and start its first build."""
    s = get_state()
    payload: dict[str, Any] = {"slug": slug, "repo_url": repo, "app_type": app_type.value}
    payload.update(
        settings_payload(
            branch=branch,
            main_file=main_file,
            python_version=python_version,
            build_command=build_command,
            output_dir=output_dir,
            public=public,
            allowed_groups=allowed_group,
            owner_groups=owner_group,
            tags=tag,
            hibernate=hibernate,
            hibernate_after_seconds=hibernate_after_seconds,
            poll=poll,
            poll_interval_seconds=poll_interval_seconds,
        )
    )
    if secrets_file is not None:
        from .secrets import read_secrets

        payload["secrets_toml"] = read_secrets(secrets_file)
    created = s.client.post("/apps", json=payload)
    _report(f"created {created['slug']} ({created['url']})")
    if wait or follow:
        created = waiting.wait_for_rollout(
            s.client,
            {**created, "current_build_id": None},
            timeout=timeout,
            follow=follow,
            progress=not s.quiet,
        )
    show_app(created)


REBUILD_FIELDS = ("branch", "main_file", "python_version", "build_command", "output_dir")


@apps_app.command("update")
def update_app(
    app: str = APP_ARG,
    branch: str | None = BRANCH,
    main_file: str | None = MAIN_FILE,
    python_version: str | None = PYTHON,
    build_command: str | None = BUILD_COMMAND,
    output_dir: str | None = OUTPUT_DIR,
    public: bool | None = PUBLIC,
    allowed_group: list[str] = ALLOWED,
    owner_group: list[str] = OWNERS,
    tag: list[str] = TAGS,
    hibernate: bool | None = HIBERNATE,
    hibernate_after_seconds: int | None = HIBERNATE_AFTER,
    poll: bool | None = POLL,
    poll_interval_seconds: int | None = POLL_INTERVAL,
    wait: bool = wait_option("the rebuild, if one is needed,"),
    follow: bool = typer.Option(False, "--follow", help="Stream build logs while waiting"),
    timeout: float = timeout_option(),
) -> None:
    """Change an app's settings. Changing the branch, main file, Python
    version, build command or output dir triggers a rebuild."""
    s = get_state()
    payload = settings_payload(
        branch=branch,
        main_file=main_file,
        python_version=python_version,
        build_command=build_command,
        output_dir=output_dir,
        public=public,
        allowed_groups=allowed_group,
        owner_groups=owner_group,
        tags=tag,
        hibernate=hibernate,
        hibernate_after_seconds=hibernate_after_seconds,
        poll=poll,
        poll_interval_seconds=poll_interval_seconds,
    )
    if not payload:
        raise usage("nothing to update: pass at least one setting (see --help)")
    before = resolve_app(s.client, app)
    updated = s.client.patch(f"/apps/{before['id']}", json=payload)
    rebuild = any(updated.get(f) != before.get(f) for f in REBUILD_FIELDS)
    _report(f"updated {updated['slug']}" + ("; rebuild scheduled" if rebuild else ""))
    if rebuild and (wait or follow):
        updated = waiting.wait_for_rollout(
            s.client, before, timeout=timeout, follow=follow, progress=not s.quiet
        )
    show_app(updated)


@apps_app.command("delete")
def delete_app(
    app: str = APP_ARG,
    yes: bool = yes_option(),
    wait: bool = wait_option("the app and its resources are gone; it"),
    timeout: float = timeout_option("5m"),
) -> None:
    """Delete an app and all its resources."""
    s = get_state()
    target = resolve_app(s.client, app)
    s.confirm(f"Delete app {target['slug']} and all its resources?", yes)
    result = s.client.delete(f"/apps/{target['id']}")
    _report(f"deleting {target['slug']}")
    if wait:
        result = waiting.wait_for_state(
            s.client, target, target="deleted", timeout=timeout, progress=not s.quiet
        )
    if s.fmt == "json":
        emit(result, "json")
    elif s.fmt == "name":
        print(target["slug"])


@apps_app.command("open")
def open_app(app: str = APP_ARG) -> None:
    """Open the app in a browser (prints the URL when non-interactive)."""
    s = get_state()
    target = resolve_app(s.client, app)
    print(target["url"])
    if s.interactive:
        webbrowser.open(target["url"])


# -- lifecycle verbs ------------------------------------------------------------


def deploy(
    app: str = APP_ARG,
    wait: bool = wait_option("the build and rollout"),
    follow: bool = typer.Option(
        False, "--follow", help="Stream build logs to stderr while waiting (implies --wait)"
    ),
    timeout: float = timeout_option(),
) -> None:
    """Rebuild from the head of the tracked branch and redeploy."""
    s = get_state()
    before = resolve_app(s.client, app)
    result = s.client.post(f"/apps/{before['id']}/deploy")
    _report(f"{before['slug']}: {result.get('status', 'deploy scheduled')}")
    if wait or follow:
        show_app(
            waiting.wait_for_rollout(
                s.client, before, timeout=timeout, follow=follow, progress=not s.quiet
            )
        )
    elif s.fmt == "json":
        emit(result, "json")


def reboot(
    app: str = APP_ARG,
    wait: bool = wait_option("the app is running again; it"),
    timeout: float = timeout_option("5m"),
) -> None:
    """Restart the app without rebuilding (clears in-memory state and caches)."""
    s = get_state()
    before = resolve_app(s.client, app)
    result = s.client.post(f"/apps/{before['id']}/reboot")
    _report(f"{before['slug']}: {result.get('status', 'reboot scheduled')}")
    if wait:
        show_app(waiting.wait_for_reboot(s.client, before, timeout=timeout, progress=not s.quiet))
    elif s.fmt == "json":
        emit(result, "json")


def wake(
    app: str = APP_ARG,
    wait: bool = wait_option("the app is running; it"),
    timeout: float = timeout_option("5m"),
) -> None:
    """Wake a hibernating app."""
    s = get_state()
    target = resolve_app(s.client, app)
    result = s.client.post(f"/apps/{target['id']}/wake")
    _report(f"{target['slug']}: {result.get('status', 'waking')}")
    if wait:
        show_app(
            waiting.wait_for_state(
                s.client, target, target="running", timeout=timeout, progress=not s.quiet
            )
        )
    elif s.fmt == "json":
        emit(result, "json")


def wait_cmd(
    app: str = APP_ARG,
    target: WaitTarget = typer.Option(WaitTarget.running, "--for", help="State to wait for"),
    timeout: float = timeout_option(),
) -> None:
    """Block until the app settles in the given state (exit 8 if it fails)."""
    s = get_state()
    current = resolve_app(s.client, app)
    result = waiting.wait_for_state(
        s.client, current, target=target.value, timeout=timeout, progress=not s.quiet
    )
    if target == WaitTarget.running:
        show_app(result)


def status(app: str = APP_ARG) -> None:
    """Show an app's state, error, URL and current build (alias of `apps get`)."""
    show_app(resolve_app(get_state().client, app))


def register(app: typer.Typer) -> None:
    app.add_typer(apps_app, name="apps")
    app.command("deploy")(deploy)
    app.command("reboot")(reboot)
    app.command("wake")(wake)
    app.command("wait")(wait_cmd)
    app.command("status")(status)
