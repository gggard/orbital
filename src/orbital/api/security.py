"""Management-plane RBAC (group-based).

Roles are resolved from OIDC group claims via the platform's group->role
mapping: admin (all apps, all actions) > creator (create apps; manage apps
whose owner_groups intersect their groups) > viewer (read-only on apps whose
owner_groups intersect their groups). Users in none of the mapped groups are
rejected at login.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..models import ApiToken, App, ensure_aware


@dataclass
class User:
    email: str
    groups: list[str]
    role: str  # "admin" | "creator" | "viewer"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def resolve_role(groups: list[str], settings: Settings) -> str | None:
    gs = set(groups)
    if gs & set(settings.admin_groups):
        return "admin"
    if gs & set(settings.creator_groups):
        return "creator"
    if gs & set(settings.viewer_groups):
        return "viewer"
    return None


def _user_from_token(token: str, db: Session, settings: Settings) -> User:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    rec = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash))
    if rec is None or rec.revoked_at is not None:
        raise HTTPException(401, "invalid API token")
    if ensure_aware(rec.expires_at) < datetime.now(UTC):
        raise HTTPException(401, "API token has expired")
    role = resolve_role(rec.groups, settings)
    if role is None:
        raise HTTPException(403, "your groups grant no access to this console")
    rec.last_used_at = datetime.now(UTC)
    return User(email=rec.email, groups=rec.groups, role=role)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    if not settings.ui_auth_enabled:
        return User(email="dev@localhost", groups=[], role="admin")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return _user_from_token(auth_header.removeprefix("Bearer ").strip(), db, settings)

    sess = request.session.get("user")
    if not sess:
        raise HTTPException(401, "not signed in")
    role = resolve_role(sess.get("groups", []), settings)
    if role is None:
        raise HTTPException(403, "your groups grant no access to this console")
    return User(email=sess.get("email", ""), groups=sess.get("groups", []), role=role)


def can_see(user: User, app: App) -> bool:
    return user.is_admin or bool(set(user.groups) & set(app.owner_groups or []))


def can_manage(user: User, app: App) -> bool:
    return user.is_admin or (user.role == "creator" and can_see(user, app))


def visible_app(user: User, app: App) -> App:
    """404 (not 403) for invisible apps: don't leak their existence."""
    if not can_see(user, app):
        raise HTTPException(404, "app not found")
    return app


def managed_app(user: User, app: App) -> App:
    visible_app(user, app)
    if not can_manage(user, app):
        raise HTTPException(403, "read-only access: your role cannot modify this app")
    return app


def require_creator(user: User) -> None:
    if user.role not in ("admin", "creator"):
        raise HTTPException(403, "your role cannot create apps")


def require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(403, "admin only")


def can_publish(user: User, settings: Settings) -> bool:
    """Whether the user may make an app public (platform policy)."""
    if not settings.public_sharing_groups or user.is_admin:
        return True
    return bool(set(user.groups) & set(settings.public_sharing_groups))


def require_publish(user: User, settings: Settings) -> None:
    if not can_publish(user, settings):
        raise HTTPException(
            403,
            "making apps public is restricted on this platform "
            f"(allowed groups: {', '.join(settings.public_sharing_groups)})",
        )
