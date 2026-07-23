from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import logbuffer
from ..config import Settings, get_settings
from ..db import get_db
from ..k8s import metrics
from ..models import App, AppState, ScanResult
from ..schemas import (
    AdminAppOut,
    AdminOverviewOut,
    AdminScanOut,
    AdminTotals,
    ScanOut,
    VulnerabilityOut,
)
from .apps import to_app_out
from .security import User, get_current_user, require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewOut)
def overview(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    require_admin(user)
    apps = db.scalars(select(App).order_by(App.created_at)).all()

    rows = []
    cpu_total = mem_total = 0.0
    running_count = 0
    for app in apps:
        sample = metrics.store.latest(app.id)
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


@router.get("/scans", response_model=list[AdminScanOut])
def scans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin(user)
    scan = db.get(ScanResult, scan_id)
    if scan is None:
        raise HTTPException(404, "scan not found")
    return list(scan.vulnerabilities)


@router.get("/logs", response_class=PlainTextResponse)
def logs(
    tail: int = 500,
    user: User = Depends(get_current_user),
):
    require_admin(user)
    lines = logbuffer.handler.tail(tail)
    return "\n".join(lines) if lines else "[no logs yet]"
