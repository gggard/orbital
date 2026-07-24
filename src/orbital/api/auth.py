"""Console OIDC login (authorization-code flow) and session endpoints."""

import logging
import secrets as pysecrets
from typing import Annotated
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import Settings, get_settings
from ..groups import known_groups
from .security import User, can_publish, get_current_user, resolve_role

log = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _endpoints(settings: Settings) -> dict[str, str]:
    base = settings.oidc_issuer_url.rstrip("/")
    return {
        "authorize": f"{base}/protocol/openid-connect/auth",
        "token": f"{base}/protocol/openid-connect/token",
        "jwks": f"{base}/protocol/openid-connect/certs",
        "logout": f"{base}/protocol/openid-connect/logout",
    }


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.ui_base_url.rstrip('/')}/api/auth/callback"


def _safe_next(next: str) -> str:
    """Restrict post-login redirect targets to same-site relative paths.

    Browsers treat backslashes as forward slashes in URLs and collapse a
    run of leading slashes/backslashes right after the first character
    into a network-path (authority) reference - e.g. ``///evil.com`` or
    ``/\\evil.com`` still navigate off-site even though urlparse() alone
    sees an empty netloc for those, so that run is rejected outright
    rather than trusted to urlparse(). The scheme/netloc check on top
    rules out absolute URLs (``https://evil.com``); together they mean
    the ``next`` query param can't be used for open-redirect phishing.
    """
    normalized = next.replace("\\", "/")
    if not normalized.startswith("/") or normalized.startswith("//"):
        return "/"
    parsed = urlparse(normalized)
    if parsed.scheme or parsed.netloc:
        return "/"
    return normalized


def _verify_id_token(id_token: str, settings: Settings) -> dict:
    jwks_url = _endpoints(settings)["jwks"]
    client = _jwks_clients.setdefault(jwks_url, jwt.PyJWKClient(jwks_url))
    key = client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        key.key,
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer_url.rstrip("/"),
    )


@router.get("/api/auth/login")
def login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    next: str = "/",
):
    if not settings.ui_auth_enabled:
        return RedirectResponse(_safe_next(next))
    state = pysecrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    request.session["post_login_redirect"] = _safe_next(next)
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": _redirect_uri(settings),
        "state": state,
    }
    return RedirectResponse(f"{_endpoints(settings)['authorize']}?{urlencode(params)}")


@router.get("/api/auth/callback")
def callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    code: str = "",
    state: str = "",
):
    if not code or state != request.session.pop("oauth_state", None):
        raise HTTPException(400, "invalid login callback (state mismatch)")
    try:
        resp = httpx.post(
            _endpoints(settings)["token"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(settings),
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        claims = _verify_id_token(resp.json()["id_token"], settings)
    except (httpx.HTTPError, jwt.PyJWTError, KeyError) as e:
        log.warning("login failed: %s", e)
        raise HTTPException(502, f"login failed: {e}")

    email = claims.get("email", claims.get("preferred_username", ""))
    groups = [g for g in claims.get("groups", []) if isinstance(g, str)]
    request.session["user"] = {"email": email, "groups": groups}
    # kept for RP-initiated logout (id_token_hint), so signing out also ends
    # the Keycloak SSO session
    request.session["id_token"] = resp.json()["id_token"]
    log.info("console login: %s (groups=%s, role=%s)",
             email, groups, resolve_role(groups, settings))
    return RedirectResponse(request.session.pop("post_login_redirect", "/"))


@router.get("/api/auth/logout")
def logout(request: Request, settings: Annotated[Settings, Depends(get_settings)]):
    """Browser navigation target: clears the console session AND the IdP SSO
    session (RP-initiated logout), then returns to the console."""
    id_token = request.session.pop("id_token", None)
    request.session.clear()
    home = settings.ui_base_url.rstrip("/") + "/"
    if not settings.ui_auth_enabled or not id_token:
        return RedirectResponse(home)
    params = {
        "id_token_hint": id_token,
        "post_logout_redirect_uri": home,
        "client_id": settings.oidc_client_id,
    }
    return RedirectResponse(f"{_endpoints(settings)['logout']}?{urlencode(params)}")


@router.get("/api/v1/me")
def me(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    return {
        "authenticated": True,
        "auth_enabled": settings.ui_auth_enabled,
        "email": user.email,
        "groups": user.groups,
        "role": user.role,
        "can_create": user.role in ("admin", "creator"),
        "can_publish": can_publish(user, settings),
        "git_poll_default_interval_seconds": settings.git_poll_default_interval_seconds,
        "git_poll_min_interval_seconds": settings.git_poll_min_interval_seconds,
        "hibernation_timeout_seconds": settings.hibernation_timeout_seconds,
        "hibernation_max_timeout_seconds": settings.hibernation_max_timeout_seconds,
        "api_token_max_ttl_days": settings.api_token_max_ttl_days,
    }


@router.get("/api/v1/groups")
def groups(
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    q: str = "",
    limit: int = 100,
):
    """Known groups for the console's pickers (viewer access, ownership).

    Merged from the role config, ORBITAL_KNOWN_GROUPS, and (when enabled) the
    Keycloak realm's group list. ``q`` filters by case-insensitive substring;
    ``limit`` caps the response so huge directories stay usable. Advisory
    only — free-typed group names are still accepted everywhere.
    """
    names = known_groups(settings)
    if q:
        needle = q.lower()
        names = [n for n in names if needle in n.lower()]
    return {"groups": names[: max(1, min(limit, 1000))]}
