"""Per-app authorization endpoint, used as nginx ingress `auth-url` (SPEC §5.5).

Flow for a private app:
  browser -> ingress -> auth_request GET /authz/{app_id} (cookies forwarded)
  -> we validate the session against oauth2-proxy /oauth2/auth
  -> 200 if the user's OIDC groups intersect the app's allowed_groups
     (or the list is empty = any authenticated user), 401 to trigger the
     sign-in redirect, 403 if authenticated but not allowed.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from .. import activity, analytics
from ..config import Settings, get_settings
from ..db import get_db
from ..models import App

log = logging.getLogger(__name__)

router = APIRouter(tags=["authz"])


def check_session(auth_url: str, cookie: str) -> tuple[bool, str, list[str]]:
    """Ask oauth2-proxy whether the session cookie is valid.

    Returns (authenticated, email, groups).
    """
    try:
        r = httpx.get(auth_url, headers={"Cookie": cookie}, timeout=5)
    except httpx.HTTPError as e:
        log.warning("oauth2-proxy unreachable: %s", e)
        return False, "", []
    if r.status_code != 202:
        return False, "", []
    email = r.headers.get("x-auth-request-email", "")
    groups = [g.strip() for g in r.headers.get("x-auth-request-groups", "").split(",") if g.strip()]
    return True, email, groups


@router.get("/authz/{app_id}")
def authz(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    app = db.get(App, app_id)
    if app is None:
        return Response(status_code=404)
    activity.touch(app)
    if app.public:
        # public apps set no cookies to identify viewers by (FR-7.2); an
        # anonymous, IP-deduped view is all we can record here
        analytics.record_view(db, app, viewer=None, viewer_key=analytics.client_key(request))
        return Response(status_code=200)
    if not settings.oauth2_proxy_auth_url:
        log.error("private app %s requested but oauth2_proxy_auth_url not configured", app.slug)
        return Response(status_code=503)

    authenticated, email, groups = check_session(
        settings.oauth2_proxy_auth_url, request.headers.get("cookie", "")
    )
    if not authenticated:
        return Response(status_code=401)

    allowed = app.allowed_groups or []
    if not allowed or set(groups) & set(allowed):
        # private-app viewers are identified (FR-7.2)
        analytics.record_view(db, app, viewer=email, viewer_key=email)
        return Response(status_code=200)
    log.info("denied %s for %s (groups=%s, allowed=%s)", app.slug, email, groups, allowed)
    return Response(status_code=403)
