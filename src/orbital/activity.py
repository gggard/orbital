"""Shared helpers for recording app activity (SPEC §4.8) and the fleet-wide
recent-activity feed shown on the console home page.
"""

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import App, Event

# Upper bound on stored events - this feeds a short "recent activity" rail,
# not an audit log, so history beyond this is trimmed on every write rather
# than left to grow the table unbounded.
MAX_EVENTS = 200


def touch(app: App) -> None:
    """Mark an app as having just seen traffic; resets its idle clock."""
    app.last_active_at = datetime.now(UTC)


def record(session: Session, slug: str, text: str, level: str, actor: str) -> None:
    """Append one row to the recent-activity feed and trim old history."""
    session.add(Event(slug=slug, text=text, level=level, actor=actor))
    session.flush()
    count = session.scalar(select(func.count()).select_from(Event))
    if count and count > MAX_EVENTS:
        stale_ids = session.scalars(
            select(Event.id).order_by(Event.created_at.desc()).offset(MAX_EVENTS)
        ).all()
        if stale_ids:
            session.execute(delete(Event).where(Event.id.in_(stale_ids)))
