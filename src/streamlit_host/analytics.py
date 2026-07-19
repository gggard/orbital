"""Records per-app view events and aggregates them for the dashboard (SPEC §4.7).

Views are recorded at the existing activity-beacon touchpoints (`/activity`
for public apps, `/authz` for private apps - see `api/wake.py` /
`api/authz.py`), which already fire on every real request via the ingress
`auth-url`/beacon annotations added for hibernation (§4.8, `k8s/resources.py`).
No new ingress wiring is needed.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import App, ViewEvent, ensure_aware
from .schemas import AnalyticsDailyPoint, AnalyticsOut, AnalyticsViewer

# A single page load fires several beacon pings in quick succession (the
# initial document, static assets, the websocket upgrade). Debouncing
# same-viewer pings within this window turns those into one "view" -
# matching the common analytics definition of a session.
DEDUPE_WINDOW = timedelta(minutes=30)


def client_key(request: Request) -> str:
    """Best-effort anonymous identity for public-app viewers (SPEC FR-7.2):
    no cookies are set, so the real client IP (as forwarded by the ingress)
    is used purely as a server-side dedup key - it is never exposed via the API.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def record_view(session: Session, app: App, *, viewer: str | None, viewer_key: str) -> None:
    if not viewer_key:
        return
    cutoff = datetime.now(UTC) - DEDUPE_WINDOW
    recent = session.scalar(
        select(ViewEvent.id)
        .where(
            ViewEvent.app_id == app.id,
            ViewEvent.viewer_key == viewer_key,
            ViewEvent.viewed_at >= cutoff,
        )
        .limit(1)
    )
    if recent is not None:
        return
    session.add(ViewEvent(app_id=app.id, viewer=viewer, viewer_key=viewer_key))


def summary(session: Session, app: App, *, days: int = 30) -> AnalyticsOut:
    """Aggregate view events into headline stats + a daily trend + named viewers.

    Aggregation happens in Python rather than via DB-specific date-bucketing
    (`date_trunc`/`strftime`) so it works unchanged on both sqlite (dev) and
    postgres (prod) - fine at this volume (one row per deduped visit).
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(days=days)

    total_views = (
        session.scalar(
            select(func.count()).select_from(ViewEvent).where(ViewEvent.app_id == app.id)
        )
        or 0
    )
    last_viewed_at = session.scalar(
        select(func.max(ViewEvent.viewed_at)).where(ViewEvent.app_id == app.id)
    )
    if last_viewed_at is not None:
        last_viewed_at = ensure_aware(last_viewed_at)

    rows = session.scalars(
        select(ViewEvent)
        .where(ViewEvent.app_id == app.id, ViewEvent.viewed_at >= window_start)
        .order_by(ViewEvent.viewed_at)
    ).all()

    daily: dict[str, dict] = {}
    viewers: dict[str, dict] = {}
    unique_1d: set[str] = set()
    unique_7d: set[str] = set()
    cutoff_1d, cutoff_7d = now - timedelta(days=1), now - timedelta(days=7)

    for row in rows:
        viewed_at = ensure_aware(row.viewed_at)
        day = viewed_at.date().isoformat()
        bucket = daily.setdefault(day, {"views": 0, "keys": set()})
        bucket["views"] += 1
        bucket["keys"].add(row.viewer_key)

        if viewed_at >= cutoff_1d:
            unique_1d.add(row.viewer_key)
        if viewed_at >= cutoff_7d:
            unique_7d.add(row.viewer_key)

        if row.viewer:
            v = viewers.setdefault(row.viewer, {"views": 0, "last_seen": viewed_at})
            v["views"] += 1
            v["last_seen"] = max(v["last_seen"], viewed_at)

    daily_series = [
        AnalyticsDailyPoint(date=day, views=b["views"], unique_viewers=len(b["keys"]))
        for day, b in sorted(daily.items())
    ]
    viewer_list = [
        AnalyticsViewer(viewer=email, views=v["views"], last_seen=v["last_seen"])
        for email, v in sorted(viewers.items(), key=lambda kv: kv[1]["last_seen"], reverse=True)
    ]

    return AnalyticsOut(
        total_views=total_views,
        unique_viewers_1d=len(unique_1d),
        unique_viewers_7d=len(unique_7d),
        unique_viewers_30d=len({k for b in daily.values() for k in b["keys"]}),
        last_viewed_at=last_viewed_at,
        daily=daily_series,
        viewers=viewer_list,
    )
