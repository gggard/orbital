"""Management-plane RBAC (group-based).

Roles are resolved from OIDC group claims via the platform's group->role
mapping: admin (all apps, all actions) > creator (create apps; manage apps
whose owner_groups intersect their groups) > viewer (read-only on apps whose
owner_groups intersect their groups). Users in none of the mapped groups are
rejected at login.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from ..config import Settings, get_settings
from ..models import App


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


def get_current_user(
    request: Request, settings: Settings = Depends(get_settings)
) -> User:
    if not settings.ui_auth_enabled:
        return User(email="dev@localhost", groups=[], role="admin")
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
