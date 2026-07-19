import tomllib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..k8s import inspect, metrics
from ..models import App, AppState, Build, PendingAction
from ..schemas import (
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


def _get_app(db: Session, app_id: str) -> App:
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(404, "app not found")
    return app


def _visible(db: Session, app_id: str, user: User) -> App:
    return visible_app(user, _get_app(db, app_id))


def _managed(db: Session, app_id: str, user: User) -> App:
    return managed_app(user, _get_app(db, app_id))


def _to_out(app: App, settings: Settings) -> AppOut:
    return AppOut(
        id=app.id,
        slug=app.slug,
        repo_url=app.repo_url,
        branch=app.branch,
        main_file=app.main_file,
        python_version=app.python_version,
        public=app.public,
        allowed_groups=app.allowed_groups or [],
        owner_groups=app.owner_groups or [],
        state=app.state,
        error=app.error,
        current_build_id=app.current_build_id,
        url=settings.app_url(app.slug),
        webhook_path=f"/webhooks/apps/{app.id}/{app.webhook_token}",
        hibernate_enabled=app.hibernate_enabled,
        hibernate_after_seconds=app.hibernate_after_seconds,
        last_active_at=app.last_active_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _validate_toml(text: str):
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise HTTPException(422, f"invalid TOML: {e}")


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
    python_version = payload.python_version or settings.default_python_version
    if python_version not in settings.python_versions:
        raise HTTPException(
            422,
            f"unsupported python version {python_version!r}; "
            f"supported: {sorted(settings.python_versions)}",
        )
    if payload.secrets_toml:
        _validate_toml(payload.secrets_toml)
    app = App(
        slug=payload.slug,
        repo_url=payload.repo_url,
        branch=payload.branch,
        main_file=payload.main_file,
        python_version=python_version,
        public=payload.public,
        allowed_groups=payload.allowed_groups,
        owner_groups=owner_groups,
        secrets_toml=payload.secrets_toml,
        state=AppState.created,
        pending_action=PendingAction.deploy,
        hibernate_enabled=payload.hibernate_enabled,
        hibernate_after_seconds=payload.hibernate_after_seconds,
    )
    db.add(app)
    db.flush()
    return _to_out(app, settings)


@router.get("/apps", response_model=list[AppOut])
def list_apps(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    from .security import can_see

    apps = db.scalars(select(App).order_by(App.created_at)).all()
    return [_to_out(a, settings) for a in apps if can_see(user, a)]


@router.get("/apps/{app_id}", response_model=AppOut)
def get_app(
    app_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    return _to_out(_visible(db, app_id, user), settings)


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
    for field in ("branch", "main_file", "python_version"):
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
    if payload.hibernate_enabled is not None:
        app.hibernate_enabled = payload.hibernate_enabled
    if payload.hibernate_after_seconds is not None:
        app.hibernate_after_seconds = payload.hibernate_after_seconds
    if needs_rebuild and app.state != AppState.building:
        app.pending_action = PendingAction.deploy
    return _to_out(app, settings)


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
