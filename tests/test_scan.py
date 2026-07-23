"""Tests for the vulnerability-scanning reconciler flow (_maybe_scan et al.),
mirroring tests/test_stuck_build.py's conventions for the build flow.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbital.config import get_settings
from orbital.models import App, AppState, AppType, PendingAction, ScanResult, ScanStatus


def make_app(current_image="localhost:5000/apps/abc123def456:bld1", **kwargs) -> App:
    defaults = dict(
        id="abc123def456",
        slug="demo",
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        state=AppState.running,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
        current_build_id="bld1",
        current_image=current_image,
    )
    defaults.update(kwargs)
    return App(**defaults)


def _job(conditions=None, succeeded=None, failed=None):
    return SimpleNamespace(
        status=SimpleNamespace(conditions=conditions, succeeded=succeeded, failed=failed)
    )


@pytest.fixture
def reconciler(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from orbital import db as db_mod
    from orbital.k8s import client as k8s_client
    from orbital.k8s.reconciler import Reconciler

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    for name in ("batch", "apps_v1", "core", "networking"):
        monkeypatch.setattr(k8s_client, name, MagicMock())
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _mock_k8s(monkeypatch, job=None, pod_log=""):
    from orbital.k8s import client as k8s_client

    batch, apps_v1, core, networking = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    if job is not None:
        batch.read_namespaced_job.return_value = job
    core.list_namespaced_pod.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="scan-pod"))]
    )
    log_resp = MagicMock()
    log_resp.data = pod_log.encode()
    core.read_namespaced_pod_log.return_value = log_resp
    monkeypatch.setattr(k8s_client, "batch", lambda: batch)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)
    monkeypatch.setattr(k8s_client, "networking", lambda: networking)
    return batch, apps_v1, core, networking


def _persist(app: App, scan: ScanResult | None = None) -> str:
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
        if scan is not None:
            session.add(scan)
            session.flush()
            app.last_scan_id = scan.id
    return app.id


def _scan(status=ScanStatus.running, image="localhost:5000/apps/abc123def456:bld1", **kwargs):
    defaults = dict(
        id="scan00000001",
        app_id="abc123def456",
        build_id="bld1",
        image=image,
        status=status,
        created_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return ScanResult(**defaults)


REPORT = """
{"Results": [{"Target": "demo", "Vulnerabilities": [
  {"VulnerabilityID": "CVE-2024-0001", "PkgName": "libfoo", "InstalledVersion": "1.0",
   "FixedVersion": "1.1", "Severity": "CRITICAL", "Title": "bad thing"}
]}]}
"""


# -- starting a scan ---------------------------------------------------------


def test_maybe_scan_starts_a_scan_when_none_exists(reconciler, monkeypatch):
    _mock_k8s(monkeypatch)
    app_id = _persist(make_app())

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id is not None
        scan = session.get(ScanResult, app.last_scan_id)
        assert scan.status == ScanStatus.running
        assert scan.image == app.current_image


def test_maybe_scan_does_nothing_without_a_current_image(reconciler, monkeypatch):
    _mock_k8s(monkeypatch)
    app_id = _persist(make_app(current_image=None))

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id is None


def test_maybe_scan_skips_when_recent_scan_of_same_image_exists(reconciler, monkeypatch):
    batch, *_ = _mock_k8s(monkeypatch)
    scan = _scan(status=ScanStatus.succeeded, finished_at=datetime.now(UTC))
    app_id = _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id == scan.id  # unchanged - no new scan started
    batch.create_namespaced_job.assert_not_called()


def test_maybe_scan_starts_new_scan_when_image_changed(reconciler, monkeypatch):
    _mock_k8s(monkeypatch)
    scan = _scan(
        status=ScanStatus.succeeded,
        image="localhost:5000/apps/abc123def456:old",
        finished_at=datetime.now(UTC),
    )
    app_id = _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id != scan.id
        new_scan = session.get(ScanResult, app.last_scan_id)
        assert new_scan.image == app.current_image


def test_maybe_scan_honors_on_demand_request_even_if_not_due(reconciler, monkeypatch):
    _mock_k8s(monkeypatch)
    scan = _scan(status=ScanStatus.succeeded, finished_at=datetime.now(UTC))
    app_id = _persist(make_app(scan_requested_at=datetime.now(UTC)), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id != scan.id
        assert app.scan_requested_at is None


def test_maybe_scan_does_not_start_second_scan_while_one_in_flight(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=None)
    batch, *_ = _mock_k8s(monkeypatch, job=job)
    scan = _scan(status=ScanStatus.running)
    app_id = _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._maybe_scan(session, app)
        assert app.last_scan_id == scan.id
    batch.create_namespaced_job.assert_not_called()


# -- checking an in-flight scan ----------------------------------------------


def test_check_scan_succeeds_via_status_succeeded_and_parses_report(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=1)
    _mock_k8s(monkeypatch, job=job, pod_log=REPORT)
    scan = _scan()
    _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        s = session.get(ScanResult, scan.id)
        reconciler._check_scan(session, s)
        assert s.status == ScanStatus.succeeded
        assert s.critical_count == 1
        assert len(s.vulnerabilities) == 1
        assert s.vulnerabilities[0].vuln_id == "CVE-2024-0001"


def test_check_scan_fails_via_status_failed(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=1)
    _mock_k8s(monkeypatch, job=job)
    scan = _scan()
    _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        s = session.get(ScanResult, scan.id)
        reconciler._check_scan(session, s)
        assert s.status == ScanStatus.failed
        assert s.error


def test_check_scan_times_out_with_no_terminal_signal(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=None)
    _mock_k8s(monkeypatch, job=job)
    settings = get_settings()
    stale = datetime.now(UTC) - timedelta(seconds=settings.scan_timeout_seconds + 61)
    scan = _scan(created_at=stale)
    _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        s = session.get(ScanResult, scan.id)
        reconciler._check_scan(session, s)
        assert s.status == ScanStatus.failed
        assert "timed out" in s.error


def test_check_scan_job_not_found_fails_scan(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client
    from kubernetes.client import ApiException

    batch = MagicMock()
    batch.read_namespaced_job.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s_client, "batch", lambda: batch)
    scan = _scan()
    _persist(make_app(), scan=scan)

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        s = session.get(ScanResult, scan.id)
        reconciler._check_scan(session, s)
        assert s.status == ScanStatus.failed
        assert "not found" in s.error


# -- retention ----------------------------------------------------------------


def test_prune_old_scans_keeps_only_the_retention_limit(reconciler, monkeypatch):
    _mock_k8s(monkeypatch)
    app = make_app()
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
        session.flush()
        for i in range(15):
            session.add(
                _scan(
                    id=f"scan{i:08d}",
                    status=ScanStatus.succeeded,
                    finished_at=datetime.now(UTC) + timedelta(seconds=i),
                )
            )
        app_id = app.id

    settings = get_settings()
    with db_mod.session_scope() as session:
        reconciler._prune_old_scans(session, app_id)

    with db_mod.session_scope() as session:
        remaining = session.query(ScanResult).filter(ScanResult.app_id == app_id).count()
        assert remaining == settings.scan_retention_per_app
