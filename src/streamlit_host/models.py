import enum
import secrets as pysecrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


class AppState(str, enum.Enum):
    created = "created"
    building = "building"
    deploying = "deploying"
    running = "running"
    sleeping = "sleeping"
    build_failed = "build_failed"
    deploy_failed = "deploy_failed"
    deleting = "deleting"


class PendingAction(str, enum.Enum):
    none = "none"
    deploy = "deploy"
    reboot = "reboot"
    delete = "delete"


class BuildPhase(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Base(DeclarativeBase):
    pass


class App(Base):
    __tablename__ = "apps"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    repo_url: Mapped[str] = mapped_column(String(500))
    branch: Mapped[str] = mapped_column(String(200), default="main")
    main_file: Mapped[str] = mapped_column(String(500), default="streamlit_app.py")
    python_version: Mapped[str] = mapped_column(String(10), default="3.12")
    public: Mapped[bool] = mapped_column(default=True)
    # OIDC groups allowed to open a private app; empty = any authenticated user
    allowed_groups: Mapped[list | None] = mapped_column(JSON, default=list)
    # management RBAC: groups whose members can see (and, with the creator
    # role, manage) this app; admins always see everything
    owner_groups: Mapped[list | None] = mapped_column(JSON, default=list)

    state: Mapped[AppState] = mapped_column(Enum(AppState), default=AppState.created)
    pending_action: Mapped[PendingAction] = mapped_column(
        Enum(PendingAction), default=PendingAction.deploy
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)

    secrets_toml: Mapped[str | None] = mapped_column(Text, default=None)
    secrets_dirty: Mapped[bool] = mapped_column(default=False)

    webhook_token: Mapped[str] = mapped_column(
        String(64), default=lambda: pysecrets.token_urlsafe(24)
    )

    current_build_id: Mapped[str | None] = mapped_column(String(12), default=None)
    current_image: Mapped[str | None] = mapped_column(String(500), default=None)

    # Hibernation (SPEC §4.8): per-app opt-out and timeout override. None
    # timeout means "use the platform default" (Settings.hibernation_timeout_seconds).
    hibernate_enabled: Mapped[bool] = mapped_column(default=True)
    hibernate_after_seconds: Mapped[int | None] = mapped_column(default=None)
    # bumped on every request while running; the reconciler compares this
    # against the timeout to decide when to scale to zero
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # set by the wake path (ingress-facing interstitial) while sleeping; the
    # reconciler clears it once it has scaled the app back up
    wake_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    builds: Mapped[list["Build"]] = relationship(
        back_populates="app", cascade="all, delete-orphan", order_by="Build.created_at"
    )
    views: Mapped[list["ViewEvent"]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uuid)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"), index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), default=None)
    image: Mapped[str | None] = mapped_column(String(500), default=None)
    phase: Mapped[BuildPhase] = mapped_column(Enum(BuildPhase), default=BuildPhase.pending)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    app: Mapped[App] = relationship(back_populates="builds")


class ViewEvent(Base):
    """A recorded view of a running app (SPEC §4.7). One row per deduped visit."""

    __tablename__ = "view_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id"), index=True)
    # authenticated viewer email for private apps; None for anonymous public
    # views (SPEC FR-7.2 - public viewers are counted, not identified)
    viewer: Mapped[str | None] = mapped_column(String(255), default=None)
    # dedup/uniqueness key: the viewer's email if known, else a client IP -
    # never returned by the API, only used to bucket "unique viewers"
    viewer_key: Mapped[str] = mapped_column(String(255), index=True)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )

    app: Mapped[App] = relationship(back_populates="views")
