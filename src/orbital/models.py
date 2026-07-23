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


def ensure_aware(dt: datetime) -> datetime:
    """sqlite drops the UTC offset on DateTime(timezone=True) round-trips
    (postgres doesn't). Every write in this app is UTC via `_now()`/
    `datetime.now(UTC)`, so a naive read is always UTC too - attach it back
    rather than let it blow up a comparison against an aware `datetime.now()`.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class AppType(str, enum.Enum):
    streamlit = "streamlit"
    static = "static"


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
    # Immutable after creation - changing type requires delete+recreate.
    app_type: Mapped[AppType] = mapped_column(Enum(AppType), default=AppType.streamlit)
    main_file: Mapped[str | None] = mapped_column(String(500), default=None)
    python_version: Mapped[str | None] = mapped_column(String(10), default=None)
    # static apps only: shell command run in an npm build stage; None means
    # no build step, serve output_dir from the repo as-is
    build_command: Mapped[str | None] = mapped_column(String(500), default=None)
    # static apps only: directory served (repo-relative, or build-stage
    # output-relative when build_command is set)
    output_dir: Mapped[str] = mapped_column(String(500), default=".")
    public: Mapped[bool] = mapped_column(default=True)
    # OIDC groups allowed to open a private app; empty = any authenticated user
    allowed_groups: Mapped[list | None] = mapped_column(JSON, default=list)
    # management RBAC: groups whose members can see (and, with the creator
    # role, manage) this app; admins always see everything
    owner_groups: Mapped[list | None] = mapped_column(JSON, default=list)
    # free-form labels for organizing/filtering the app list (SPEC-adjacent
    # feature, not RBAC - any value is accepted, see apps._normalize_tags)
    tags: Mapped[list] = mapped_column(JSON, default=list)

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

    # Git polling fallback (SPEC §4.2/FR-2.2): opt-in, for git hosts that
    # can't reach the cluster with a push webhook. None interval means "use
    # the platform default" (Settings.git_poll_default_interval_seconds).
    poll_enabled: Mapped[bool] = mapped_column(default=False)
    poll_interval_seconds: Mapped[int | None] = mapped_column(default=None)
    # bumped every time the reconciler checks the remote branch head, so it
    # only calls `git ls-remote` once per interval rather than every tick
    last_polled_at: Mapped[datetime | None] = mapped_column(
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


class ApiToken(Base):
    """Personal API token (SPEC: "dashboard session or personal API token").

    ``groups`` is a snapshot of the issuing user's OIDC groups at creation
    time; role is re-derived from it against the *current* role mapping at
    verification time rather than stored, so admin changes to the group->role
    mapping take effect immediately without reissuing tokens.
    """

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    groups: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


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
