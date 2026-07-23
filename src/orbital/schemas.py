import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import AppState, AppType, BuildPhase

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class AppCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=63)
    repo_url: str
    branch: str = "main"
    app_type: AppType = AppType.streamlit
    main_file: str | None = None  # streamlit only; defaults to "streamlit_app.py"
    python_version: str | None = None  # streamlit only
    build_command: str | None = None  # static only; None = serve output_dir as-is
    output_dir: str = "."  # static only
    public: bool = True
    allowed_groups: list[str] = []
    owner_groups: list[str] | None = None  # default: the creator's groups
    tags: list[str] = []
    secrets_toml: str | None = None
    hibernate_enabled: bool = True
    hibernate_after_seconds: int | None = Field(default=None, gt=0)
    poll_enabled: bool = False
    poll_interval_seconds: int | None = Field(default=None, gt=0)

    @field_validator("slug")
    @classmethod
    def slug_dns_safe(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug must be lowercase DNS-safe: [a-z0-9-]")
        return v

    @model_validator(mode="after")
    def _type_specific_fields(self) -> "AppCreate":
        if self.app_type == AppType.streamlit:
            if self.main_file is None:
                self.main_file = "streamlit_app.py"
            if self.build_command is not None:
                raise ValueError("build_command is only valid for static apps")
            if self.output_dir != ".":
                raise ValueError("output_dir is only valid for static apps")
        else:
            if self.main_file is not None:
                raise ValueError("main_file is only valid for streamlit apps")
            if self.python_version is not None:
                raise ValueError("python_version is only valid for streamlit apps")
            if self.secrets_toml:
                raise ValueError("secrets_toml is not supported for static apps")
        return self


class AppUpdate(BaseModel):
    branch: str | None = None
    main_file: str | None = None
    python_version: str | None = None
    build_command: str | None = None
    output_dir: str | None = None
    public: bool | None = None
    allowed_groups: list[str] | None = None
    owner_groups: list[str] | None = None
    tags: list[str] | None = None
    hibernate_enabled: bool | None = None
    hibernate_after_seconds: int | None = Field(default=None, gt=0)
    poll_enabled: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, gt=0)


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
    app_type: AppType
    main_file: str | None
    python_version: str | None
    build_command: str | None
    output_dir: str
    public: bool
    allowed_groups: list[str]
    owner_groups: list[str]
    tags: list[str]
    state: AppState
    error: str | None
    current_build_id: str | None
    url: str
    webhook_path: str
    hibernate_enabled: bool
    hibernate_after_seconds: int | None
    poll_enabled: bool
    poll_interval_seconds: int | None
    last_polled_at: datetime | None
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


class AdminAppOut(AppOut):
    cpu: float | None  # cores, latest sample (None: no metrics yet)
    mem: float | None  # bytes, latest sample


class AdminTotals(BaseModel):
    app_count: int
    running_count: int
    cpu: float  # sum of latest per-app samples (consumption, not a mutualized pool)
    mem: float


class AdminOverviewOut(BaseModel):
    totals: AdminTotals
    apps: list[AdminAppOut]


class AnalyticsOut(BaseModel):
    total_views: int
    unique_viewers_1d: int
    unique_viewers_7d: int
    unique_viewers_30d: int
    last_viewed_at: datetime | None
    daily: list[AnalyticsDailyPoint]  # last 30 days
    viewers: list[AnalyticsViewer]  # named viewers, most recently seen first


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ttl_days: int | None = Field(default=None, gt=0)


class TokenCreated(BaseModel):
    id: str
    name: str
    token: str  # raw secret, shown once, never retrievable again
    created_at: datetime
    expires_at: datetime


class TokenOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}
