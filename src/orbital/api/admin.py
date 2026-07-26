from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import logbuffer
from ..config import Settings, get_settings
from ..db import get_db
from ..k8s import metrics
from ..models import App, AppState, Event, ScanResult
from ..schemas import (
    AdminAppOut,
    AdminOverviewOut,
    AdminScanOut,
    AdminTotals,
    EventOut,
    ScanOut,
    VulnerabilityOut,
)
from .apps import to_app_out
from .security import User, get_current_user, require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# How many of the reconciler's in-memory samples to expose per app for the
# overview page's mini cpu/mem sparklines - short trend, not the full ~30min
# buffer the per-app Metrics tab charts (see k8s/metrics.py MAX_SAMPLES).
SPARKLINE_SAMPLES = 12

DEFAULT_ACTIVITY_LIMIT = 20
MAX_ACTIVITY_LIMIT = 100


@router.get("/overview", response_model=AdminOverviewOut)
def overview(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_admin(user)
    apps = db.scalars(select(App).order_by(App.created_at)).all()

    rows = []
    cpu_total = mem_total = 0.0
    running_count = 0
    for app in apps:
        sample = metrics.store.latest(app.id)
        series = metrics.store.series(app.id)[-SPARKLINE_SAMPLES:]
        restarts = metrics.restart_counts.get(app.id)
        if app.state == AppState.running:
            running_count += 1
        if sample is not None:
            cpu_total += sample.cpu
            mem_total += sample.mem
        rows.append(
            AdminAppOut(
                **to_app_out(app, settings).model_dump(),
                cpu=sample.cpu if sample else None,
                mem=sample.mem if sample else None,
                restarts=restarts.count if restarts else None,
                cpu_series=[s.cpu for s in series],
                mem_series=[s.mem for s in series],
            )
        )

    return AdminOverviewOut(
        totals=AdminTotals(
            app_count=len(apps),
            running_count=running_count,
            cpu=cpu_total,
            mem=mem_total,
        ),
        apps=rows,
    )


@router.get("/activity", response_model=list[EventOut])
def list_activity(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = DEFAULT_ACTIVITY_LIMIT,
):
    """Most recent fleet-wide events, newest first, for the console home
    page's "Recent activity" rail.
    """
    require_admin(user)
    limit = max(1, min(limit, MAX_ACTIVITY_LIMIT))
    events = db.scalars(select(Event).order_by(Event.created_at.desc()).limit(limit)).all()
    return events


@router.get("/scans", response_model=list[AdminScanOut])
def scans(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_admin(user)
    apps = db.scalars(select(App).order_by(App.slug)).all()
    return [
        AdminScanOut(**ScanOut.model_validate(app.scan_results[-1]).model_dump(), slug=app.slug)
        for app in apps
        if app.scan_results
    ]


@router.get("/scans/{scan_id}/vulnerabilities", response_model=list[VulnerabilityOut])
def scan_vulnerabilities(
    scan_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    require_admin(user)
    scan = db.get(ScanResult, scan_id)
    if scan is None:
        raise HTTPException(404, "scan not found")
    return list(scan.vulnerabilities)


@router.get("/logs", response_class=PlainTextResponse)
def logs(
    user: Annotated[User, Depends(get_current_user)],
    tail: int = 500,
):
    require_admin(user)
    lines = logbuffer.handler.tail(tail)
    return "\n".join(lines) if lines else "[no logs yet]"
