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
    created_at: datetime
    updated_at: datetime


class SecretsIn(BaseModel):
    secrets_toml: str
