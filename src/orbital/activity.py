"""Shared helpers for recording app activity (SPEC §4.8) and the fleet-wide
recent-activity feed shown on the console home page.
"""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, delete, select
from sqlalchemy.orm import Session

from .models import App, Event

# Per-app floor: a noisy app (a flapping build loop, aggressive git polling…)
# must never be able to evict *every* other app's history from the feed just
# by generating enough volume - each slug always keeps its own last N rows,
# trimmed before the global cap below is ever applied.
MAX_EVENTS_PER_APP = 20

# Whole-table safety cap - this feeds a short "recent activity" rail, not an
# audit log, so history beyond this is trimmed on every write rather than
# left to grow unbounded. Comfortably larger than MAX_EVENTS_PER_APP so it
# only bites when the fleet as a whole (not just one app) is very active.
MAX_EVENTS = 1000


def touch(app: App) -> None:
    """Mark an app as having just seen traffic; resets its idle clock."""
    app.last_active_at = datetime.now(UTC)


def record(session: Session, slug: str, text: str, level: str, actor: str) -> None:
    """Append one row to the recent-activity feed and trim old history.

    Trimming is two-tier: first cap this app's own history (so a noisy
    neighbor can never evict it), then cap the whole table (so total volume
    stays bounded even when many apps are active at once).
    """
    session.add(Event(slug=slug, text=text, level=level, actor=actor))
    session.flush()
    _trim(session, MAX_EVENTS_PER_APP, Event.slug == slug)
    _trim(session, MAX_EVENTS)


def _trim(session: Session, limit: int, *where: ColumnElement[bool]) -> None:
    stale_ids = session.scalars(
        select(Event.id).where(*where).order_by(Event.created_at.desc()).offset(limit)
    ).all()
    if stale_ids:
        session.execute(delete(Event).where(Event.id.in_(stale_ids)))
