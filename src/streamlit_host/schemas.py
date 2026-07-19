import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .models import AppState, BuildPhase

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class AppCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=63)
    repo_url: str
    branch: str = "main"
    main_file: str = "streamlit_app.py"
    python_version: str | None = None
    public: bool = True
    allowed_groups: list[str] = []
    owner_groups: list[str] | None = None  # default: the creator's groups
    secrets_toml: str | None = None
    hibernate_enabled: bool = True
    hibernate_after_seconds: int | None = Field(default=None, gt=0)

    @field_validator("slug")
    @classmethod
    def slug_dns_safe(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug must be lowercase DNS-safe: [a-z0-9-]")
        return v


class AppUpdate(BaseModel):
    branch: str | None = None
    main_file: str | None = None
    python_version: str | None = None
    public: bool | None = None
    allowed_groups: list[str] | None = None
    owner_groups: list[str] | None = None
    hibernate_enabled: bool | None = None
    hibernate_after_seconds: int | None = Field(default=None, gt=0)


class BuildOut(BaseModel):
    id: str
    app_id: str
    commit_sha: str | None
    image: str | None
    phase: BuildPhase
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class AppOut(BaseModel):
    id: str
    slug: str
    repo_url: str
    branch: str
    main_file: str
    python_version: str
    public: bool
    allowed_groups: list[str]
    owner_groups: list[str]
    state: AppState
    error: str | None
    current_build_id: str | None
    url: str
    webhook_path: str
    hibernate_enabled: bool
    hibernate_after_seconds: int | None
    last_active_at: datetime
    created_at: datetime
    updated_at: datetime


class SecretsIn(BaseModel):
    secrets_toml: str


class MetricsPoint(BaseModel):
    t: float  # unix seconds
    cpu: float  # cores
    mem: float  # bytes


class MetricsLimits(BaseModel):
    cpu: float  # cores
    mem: float  # bytes


class MetricsOut(BaseModel):
    available: bool  # false when metrics-server is absent or has no data yet
    limits: MetricsLimits
    current: MetricsPoint | None  # latest sample
    series: list[MetricsPoint]


class AnalyticsDailyPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    views: int
    unique_viewers: int


class AnalyticsViewer(BaseModel):
    viewer: str  # authenticated identity (private apps only, FR-7.2)
    views: int
    last_seen: datetime


class AnalyticsOut(BaseModel):
    total_views: int
    unique_viewers_1d: int
    unique_viewers_7d: int
    unique_viewers_30d: int
    last_viewed_at: datetime | None
    daily: list[AnalyticsDailyPoint]  # last 30 days
    viewers: list[AnalyticsViewer]  # named viewers, most recently seen first
