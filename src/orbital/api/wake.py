"""Wake path for hibernated apps (SPEC §4.8/§5.6).

Two entry points, both reachable only via the in-cluster wake-proxy Service
(`k8s.resources.WAKE_SERVICE_NAME`) that a sleeping app's Ingress is
repointed at — normal, awake traffic never reaches the control plane:

  - `/activity/{app_id}`: a non-blocking `auth_request` beacon attached to
    public apps' Ingress while running, purely to record activity.
  - `hibernation_middleware`: catches every other request whose Host header
    (subdomain routing) or path (path routing) resolves to a sleeping app,
    requests a wake-up, and serves an auto-refreshing interstitial.

The interstitial polls via JS instead of a blind `<meta refresh>`: once the
app is actually ready, the reconciler flips the Ingress backend from the
wake proxy to the app's own Service, which needs an ingress-nginx config
reload - and a request landing in that reload's narrow window gets a raw
502/503 from nginx, not a fresh interstitial or the app. A blind timed
reload can land there and hand the user a broken error page. Polling lets
the client retry through that window transparently and only navigate once a
real, non-transient response comes back.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import activity, analytics
from ..config import Settings, get_settings
from ..db import get_db, session_scope
from ..models import App

log = logging.getLogger(__name__)

router = APIRouter(tags=["wake"])

# marks a response as the interstitial itself (as opposed to the woken app,
# or a transient gateway error) so the polling script below can tell them
# apart - the interstitial and a gateway error can otherwise both arrive as
# plain 200s/error pages indistinguishable by status code alone.
WAKE_PENDING_HEADER = "X-Orbital-Wake"

INTERSTITIAL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<noscript><meta http-equiv="refresh" content="2"></noscript>
<title>Waking up {slug}...</title>
<style>
  body {{
    font-family: system-ui, -apple-system, sans-serif;
    display: flex; align-items: center; justify-content: center;
    height: 100vh; margin: 0; background: #0e1117; color: #fafafa;
  }}
  div {{ text-align: center; max-width: 28rem; padding: 1rem; }}
  h2 {{ margin-bottom: 0.5rem; }}
  p {{ color: #a3a8b8; }}
</style>
</head>
<body>
<div>
<h2>Waking up {slug}&hellip;</h2>
<p>This app was sleeping and is starting back up. This page refreshes automatically.</p>
</div>
<script>
(function poll() {{
  fetch(location.href, {{cache: "no-store"}}).then(function (res) {{
    // still the interstitial (not ready yet), or the ingress hit a gateway
    // error (502/503/504) mid-reload while the backend hand-off is in
    // flight: keep waiting instead of navigating into either.
    var pending = res.headers.get("{header}") || [502, 503, 504].includes(res.status);
    if (pending) {{
      setTimeout(poll, 1500);
    }} else {{
      location.reload();
    }}
  }}).catch(function () {{
    setTimeout(poll, 1500);
  }});
}})();
</script>
</body>
</html>"""


@router.get("/activity/{app_id}")
@router.post("/activity/{app_id}")
def activity_ping(app_id: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    app = db.get(App, app_id)
    if app is not None:
        activity.touch(app)
        # public apps only reach this beacon (private apps are counted in
        # authz below); no identity to record, just an anonymous view (FR-7.2)
        analytics.record_view(db, app, viewer=None, viewer_key=analytics.client_key(request))
    # always 200: this is a non-blocking auth_request beacon, never a gate
    return Response(status_code=200)


def _resolve_slug(request: Request, settings: Settings) -> str | None:
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not host:
        return None
    domain = settings.apps_domain.lower()
    if settings.routing_mode == "path":
        if host != domain:
            return None
        prefix = settings.apps_path_prefix.rstrip("/") + "/"
        path = request.url.path
        if not path.startswith(prefix):
            return None
        return path[len(prefix) :].split("/", 1)[0] or None
    suffix = f".{domain}"
    if host == domain or not host.endswith(suffix):
        return None
    return host[: -len(suffix)]


async def hibernation_middleware(request: Request, call_next):
    settings = get_settings()
    if not settings.hibernation_enabled:
        return await call_next(request)
    slug = _resolve_slug(request, settings)
    if slug is None:
        return await call_next(request)

    with session_scope() as session:
        app = session.scalar(select(App).where(App.slug == slug))
        if app is None:
            app_slug = None
        else:
            app_slug = app.slug
            app.wake_requested_at = datetime.now(UTC)

    if app_slug is None:
        return await call_next(request)
    log.info("wake requested for %s via %s", app_slug, request.url.path)
    return HTMLResponse(
        INTERSTITIAL.format(slug=app_slug, header=WAKE_PENDING_HEADER),
        status_code=200,
        headers={"Retry-After": "2", WAKE_PENDING_HEADER: "pending"},
    )
