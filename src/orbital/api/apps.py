import tomllib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analytics
from ..config import Settings, get_settings
from ..db import get_db
from ..k8s import inspect, metrics
from ..models import App, AppState, AppType, Build, PendingAction
from ..schemas import (
    AnalyticsOut,
    AppCreate,
    AppOut,
    AppUpdate,
    BuildOut,
    MetricsLimits,
    MetricsOut,
    MetricsPoint,
    SecretsIn,
)
from .security import (
    User,
    get_current_user,
    managed_app,
    require_creator,
    require_publish,
    visible_app,
)

router = APIRouter(prefix="/api/v1", tags=["apps"])

MAX_TAGS = 20
MAX_TAG_LENGTH = 40


def _normalize_tags(tags: list[str]) -> list[str]:
    """Trim whitespace, drop empties, and dedupe case-insensitively (first
    casing seen wins) - free-typed tags otherwise accumulate near-duplicates
    like "ml" / "ML" / " ml " with no autocomplete stopping them.
    """
    seen: dict[str, str] = {}
    for raw in tags:
        t = raw.strip()
        if not t:
            continue
        if len(t) > MAX_TAG_LENGTH:
            raise HTTPException(422, f"tag {t!r} exceeds {MAX_TAG_LENGTH} characters")
        seen.setdefault(t.lower(), t)
    if len(seen) > MAX_TAGS:
        raise HTTPException(422, f"at most {MAX_TAGS} tags allowed per app")
    return list(seen.values())


def _get_app(db: Session, app_id: str) -> App:
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(404, "app not found")
    return app


def _visible(db: Session, app_id: str, user: User) -> App:
    return visible_app(user, _get_app(db, app_id))


def _managed(db: Session, app_id: str, user: User) -> App:
    return managed_app(user, _get_app(db, app_id))


def to_app_out(app: App, settings: Settings) -> AppOut:
    return AppOut(
        id=app.id,
        slug=app.slug,
        repo_url=app.repo_url,
        branch=app.branch,
        app_type=app.app_type,
        main_file=app.main_file,
        python_version=app.python_version,
        build_command=app.build_command,
        output_dir=app.output_dir,
        public=app.public,
        allowed_groups=app.allowed_groups or [],
        owner_groups=app.owner_groups or [],
        tags=app.tags or [],
        state=app.state,
        error=app.error,
        current_build_id=app.current_build_id,
        url=settings.app_url(app.slug),
        webhook_path=f"/webhooks/apps/{app.id}/{app.webhook_token}",
        hibernate_enabled=app.hibernate_enabled,
        hibernate_after_seconds=app.hibernate_after_seconds,
        poll_enabled=app.poll_enabled,
        poll_interval_seconds=app.poll_interval_seconds,
        last_polled_at=app.last_polled_at,
        last_active_at=app.last_active_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _validate_toml(text: str):
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise HTTPException(422, f"invalid TOML: {e}")


def _validate_poll_interval(value: int | None, settings: Settings) -> None:
    if value is not None and value < settings.git_poll_min_interval_seconds:
        raise HTTPException(
            422,
            "poll_interval_seconds must be >= "
            f"{settings.git_poll_min_interval_seconds} (platform minimum)",
        )


def _validate_hibernate_timeout(value: int | None, settings: Settings) -> None:
    if value is not None and value > settings.hibernation_max_timeout_seconds:
        raise HTTPException(
            422,
            "hibernate_after_seconds must be <= "
            f"{settings.hibernation_max_timeout_seconds} (platform maximum)",
        )


@router.post("/apps", response_model=AppOut, status_code=201)
def create_app(
    payload: AppCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    require_creator(user)
    if payload.public:
        require_publish(user, settings)
    owner_groups = payload.owner_groups if payload.owner_groups is not None else user.groups
    if not user.is_admin and not set(owner_groups) & set(user.groups):
        raise HTTPException(
            403, "owner_groups must include at least one of your own groups"
        )
    if db.scalar(select(App).where(App.slug == payload.slug)):
        raise HTTPException(409, f"slug {payload.slug!r} already in use")
    python_version = None
    if payload.app_type == AppType.streamlit:
        python_version = payload.python_version or settings.default_python_version
        if python_version not in settings.python_versions:
            raise HTTPException(
                422,
                f"unsupported python version {python_version!r}; "
                f"supported: {sorted(settings.python_versions)}",
            )
    if payload.secrets_toml:
        _validate_toml(payload.secrets_toml)
    _validate_poll_interval(payload.poll_interval_seconds, settings)
    _validate_hibernate_timeout(payload.hibernate_after_seconds, settings)
    app = App(
        slug=payload.slug,
        repo_url=payload.repo_url,
        branch=payload.branch,
        app_type=payload.app_type,
        main_file=payload.main_file,
        python_version=python_version,
        build_command=payload.build_command,
        output_dir=payload.output_dir,
        public=payload.public,
        allowed_groups=payload.allowed_groups,
        owner_groups=owner_groups,
        tags=_normalize_tags(payload.tags),
        secrets_toml=payload.secrets_toml,
        state=AppState.created,
        pending_action=PendingAction.deploy,
        hibernate_enabled=payload.hibernate_enabled,
        hibernate_after_seconds=payload.hibernate_after_seconds,
        poll_enabled=payload.poll_enabled,
        poll_interval_seconds=payload.poll_interval_seconds,
    )
    db.add(app)
    db.flush()
    return to_app_out(app, settings)


@router.get("/apps", response_model=list[AppOut])
def list_apps(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    from .security import can_see

    apps = db.scalars(select(App).order_by(App.created_at)).all()
    return [to_app_out(a, settings) for a in apps if can_see(user, a)]


@router.get("/tags")
def list_tags(
    q: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Known tags for the console's tag pickers (create/edit forms, filter
    bar), collected from apps visible to the current user. ``q`` filters by
    case-insensitive substring; ``limit`` caps the response. Advisory only -
    free-typed tags are still accepted everywhere.
    """
    from .security import can_see

    apps = db.scalars(select(App)).all()
    names = {t for a in apps if can_see(user, a) for t in (a.tags or [])}
    if q:
        needle = q.lower()
        names = {n for n in names if needle in n.lower()}
    return {"tags": sorted(names)[: max(1, min(limit, 1000))]}


@router.get("/apps/{app_id}", response_model=AppOut)
def get_app(
    app_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    return to_app_out(_visible(db, app_id, user), settings)


@router.patch("/apps/{app_id}", response_model=AppOut)
def update_app(
    app_id: str,
    payload: AppUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    app = _managed(db, app_id, user)
    needs_rebuild = False
    if app.app_type == AppType.streamlit:
        type_fields = ("main_file", "python_version")
        other_type_fields = ("build_command", "output_dir")
    else:
        type_fields = ("build_command", "output_dir")
        other_type_fields = ("main_file", "python_version")
    for field in other_type_fields:
        if getattr(payload, field) is not None:
            raise HTTPException(422, f"{field} does not apply to {app.app_type.value} apps")
    for field in ("branch", *type_fields):
        value = getattr(payload, field)
        if value is not None and value != getattr(app, field):
            if field == "python_version" and value not in settings.python_versions:
                raise HTTPException(422, f"unsupported python version {value!r}")
            setattr(app, field, value)
            needs_rebuild = True
    # access control changes take effect live (authz reads the DB, the
    # reconciler converges the ingress) - no rebuild needed
    if payload.public is not None:
        if payload.public and not app.public:
            require_publish(user, settings)  # private -> public transition
        app.public = payload.public
    if payload.allowed_groups is not None:
        app.allowed_groups = payload.allowed_groups
    if payload.owner_groups is not None:
        if not user.is_admin:
            # owners may share ownership with other groups, but must keep at
            # least one of their own groups: no self-lockout, and full
            # transfers away require an admin
            if not payload.owner_groups:
                raise HTTPException(
                    422, "owner_groups cannot be empty (the app would become admins-only)"
                )
            if not set(payload.owner_groups) & set(user.groups):
                raise HTTPException(
                    403,
                    "owner_groups must keep at least one of your own groups "
                    "(ask an admin to transfer ownership entirely)",
                )
        app.owner_groups = payload.owner_groups
    if payload.tags is not None:
        app.tags = _normalize_tags(payload.tags)
    if payload.hibernate_enabled is not None:
        app.hibernate_enabled = payload.hibernate_enabled
    if payload.hibernate_after_seconds is not None:
        _validate_hibernate_timeout(payload.hibernate_after_seconds, settings)
        app.hibernate_after_seconds = payload.hibernate_after_seconds
    if payload.poll_enabled is not None:
        app.poll_enabled = payload.poll_enabled
    if payload.poll_interval_seconds is not None:
        _validate_poll_interval(payload.poll_interval_seconds, settings)
        app.poll_interval_seconds = payload.poll_interval_seconds
    if needs_rebuild and app.state != AppState.building:
        app.pending_action = PendingAction.deploy
    return to_app_out(app, settings)


@router.delete("/apps/{app_id}", status_code=202)
def delete_app(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = _managed(db, app_id, user)
    app.pending_action = PendingAction.delete
    app.state = AppState.deleting
    return {"status": "deleting"}


@router.post("/apps/{app_id}/deploy", status_code=202)
def deploy_app(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = _managed(db, app_id, user)
    if app.state == AppState.building:
        raise HTTPException(409, "a build is already in progress")
    app.pending_action = PendingAction.deploy
    return {"status": "deploy scheduled"}


@router.post("/apps/{app_id}/reboot", status_code=202)
def reboot_app(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = _managed(db, app_id, user)
    if app.state not in (AppState.running, AppState.deploy_failed):
        raise HTTPException(409, f"cannot reboot app in state {app.state.value}")
    app.pending_action = PendingAction.reboot
    return {"status": "reboot scheduled"}


@router.post("/apps/{app_id}/wake", status_code=202)
def wake_app(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # waking requires no more than the app's normal sharing mode (SPEC FR-8.3)
    app = _visible(db, app_id, user)
    if app.state != AppState.sleeping:
        raise HTTPException(409, f"app is not sleeping (state={app.state.value})")
    app.wake_requested_at = datetime.now(UTC)
    return {"status": "waking"}


@router.get("/apps/{app_id}/builds", response_model=list[BuildOut])
def list_builds(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = _visible(db, app_id, user)
    return list(app.builds)


@router.get("/apps/{app_id}/builds/{build_id}/logs", response_class=PlainTextResponse)
def build_logs(
    app_id: str,
    build_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    _visible(db, app_id, user)
    build = db.get(Build, build_id)
    if build is None or build.app_id != app_id:
        raise HTTPException(404, "build not found")
    live = inspect.build_log_tail(build_id, settings)
    return live or build.error or "[no logs available]"


@router.get("/apps/{app_id}/logs")
def app_logs(
    app_id: str,
    follow: bool = False,
    tail: int = 500,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    _visible(db, app_id, user)
    if follow:
        return StreamingResponse(
            inspect.app_log_stream(app_id, settings, tail=tail),
            media_type="text/plain",
        )
    return PlainTextResponse(inspect.app_log_tail(app_id, settings, tail=tail))


@router.get("/apps/{app_id}/metrics", response_model=MetricsOut)
def app_metrics(
    app_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    _visible(db, app_id, user)
    series = [
        MetricsPoint(t=s.ts, cpu=s.cpu, mem=s.mem)
        for s in metrics.store.series(app_id)
    ]
    return MetricsOut(
        available=bool(series),
        limits=MetricsLimits(
            cpu=metrics.parse_quantity(settings.app_cpu_limit),
            mem=metrics.parse_quantity(settings.app_mem_limit),
        ),
        current=series[-1] if series else None,
        series=series,
    )


@router.get("/apps/{app_id}/analytics", response_model=AnalyticsOut)
def app_analytics(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # same visibility as Metrics/Logs (SPEC FR-7.3: owner(s) and Admins - only
    # owning groups and admins can see the app at all, see security.can_see)
    app = _visible(db, app_id, user)
    return analytics.summary(db, app)


@router.get("/apps/{app_id}/secrets", response_class=PlainTextResponse)
def get_secrets(
    app_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _managed(db, app_id, user).secrets_toml or ""


@router.put("/apps/{app_id}/secrets", status_code=202)
def put_secrets(
    app_id: str,
    payload: SecretsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = _managed(db, app_id, user)
    _validate_toml(payload.secrets_toml)
    app.secrets_toml = payload.secrets_toml
    app.secrets_dirty = True
    return {"status": "secrets updated; app will restart"}
