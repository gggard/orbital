"""Shared helper for recording app activity (SPEC §4.8)."""

from datetime import UTC, datetime

from .models import App


def touch(app: App) -> None:
    """Mark an app as having just seen traffic; resets its idle clock."""
    app.last_active_at = datetime.now(UTC)
