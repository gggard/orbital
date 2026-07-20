"""Regression tests for #20: apps stuck in "building" after the underlying
Job actually finished, with the failure silently swallowed by the reconciler.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orbital.config import get_settings
from orbital.models import App, AppState, Build, BuildPhase, PendingAction


def make_app(state=AppState.building, current_build_id="bld000000001") -> App:
    return App(
        id="abc123def456",
        slug="demo",
        repo_url="https://github.com/x/y",
        branch="main",
        state=state,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
        current_build_id=current_build_id,
    )


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
    # every tick() also runs _gc_orphaned_resources (#24), which lists cluster
    # resources unconditionally - bare MagicMocks are enough since their
    # default `__iter__` makes `.items` iterate empty; this just keeps tests
    # that don't care about GC/builds from needing a live kubeconfig. Tests
    # that do care override these via _mock_k8s() below.
    for name in ("batch", "apps_v1", "core", "networking"):
        monkeypatch.setattr(k8s_client, name, MagicMock())
    r = Reconciler()
    yield r
    get_settings.cache_clear()


def _mock_k8s(monkeypatch, job):
    from orbital.k8s import client as k8s_client

    batch, apps_v1, core, networking = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    batch.read_namespaced_job.return_value = job
    core.list_namespaced_pod.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(k8s_client, "batch", lambda: batch)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)
    monkeypatch.setattr(k8s_client, "networking", lambda: networking)
    return batch, apps_v1, core, networking


def _persist(app: App, build: Build | None = None) -> str:
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        session.add(app)
        if build is not None:
            session.add(build)
    return app.id


def _build(phase=BuildPhase.running, created_at=None) -> Build:
    return Build(
        id="bld000000001",
        app_id="abc123def456",
        commit_sha="aaa111",
        phase=phase,
        created_at=created_at or datetime.now(UTC),
    )


# -- fallback to status.succeeded/status.failed when conditions lag --------


def test_check_build_succeeds_via_status_succeeded_without_complete_condition(
    reconciler, monkeypatch
):
    """The Job's "Complete" condition can lag behind the pod finishing;
    status.succeeded is bumped as soon as the pod itself completes and
    shouldn't require waiting on the condition too (issue #20)."""
    job = _job(conditions=[], succeeded=1)
    _mock_k8s(monkeypatch, job)
    app_id = _persist(make_app(), build=_build())

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._check_build(session, app)
        assert app.state == AppState.deploying
        assert app.error is None


def test_check_build_fails_via_status_failed_without_failed_condition(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=1)
    _mock_k8s(monkeypatch, job)
    app_id = _persist(make_app(), build=_build())

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._check_build(session, app)
        assert app.state == AppState.build_failed
        assert app.error


# -- time-based safety net --------------------------------------------------


def test_check_build_times_out_with_no_terminal_signal(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=None)
    _mock_k8s(monkeypatch, job)
    settings = get_settings()
    stale = datetime.now(UTC) - timedelta(
        seconds=settings.build_timeout_seconds + 121
    )
    app_id = _persist(make_app(), build=_build(created_at=stale))

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._check_build(session, app)
        assert app.state == AppState.build_failed
        assert "timed out" in app.error


def test_check_build_stays_building_within_timeout_grace(reconciler, monkeypatch):
    job = _job(conditions=[], succeeded=None, failed=None)
    _mock_k8s(monkeypatch, job)
    app_id = _persist(make_app(), build=_build(created_at=datetime.now(UTC)))

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        reconciler._check_build(session, app)
        assert app.state == AppState.building
        assert app.error is None


# -- tick() surfaces and self-heals unhandled step() exceptions ------------


def test_tick_surfaces_unhandled_step_exception_on_app(reconciler, monkeypatch):
    _persist(make_app())
    monkeypatch.setattr(
        reconciler, "step", MagicMock(side_effect=RuntimeError("boom"))
    )
    reconciler.tick()

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, "abc123def456")
        assert app.error is not None
        assert "boom" in app.error
        # state untouched - we don't guess what step() would have done
        assert app.state == AppState.building


class _CustomStrOnlyError(Exception):
    """Mimics kubernetes.client.exceptions.ApiException: overrides __str__
    with the useful detail but not __repr__, so formatting with `!r` collapses
    to a useless "ClassName()"."""

    def __str__(self):
        return "(404)\nReason: Not Found\n"


def test_tick_uses_str_not_repr_for_exceptions_with_custom_str(reconciler, monkeypatch):
    """A bare repr() on an ApiException-shaped error produced a useless
    "ApiException()" with no status/reason - str() carries the real detail."""
    _persist(make_app())
    monkeypatch.setattr(
        reconciler, "step", MagicMock(side_effect=_CustomStrOnlyError())
    )
    reconciler.tick()

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, "abc123def456")
        assert app.error is not None
        assert "Reason: Not Found" in app.error
        assert "_CustomStrOnlyError()" not in app.error


def test_tick_clears_synthetic_error_once_step_recovers(reconciler, monkeypatch):
    app_id = _persist(make_app())
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        app.error = "reconciler error: RuntimeError('boom')"

    monkeypatch.setattr(reconciler, "step", MagicMock(return_value=None))
    reconciler.tick()

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        assert app.error is None


def test_tick_does_not_clear_explicit_build_failed_error(reconciler, monkeypatch):
    app_id = _persist(make_app(state=AppState.build_failed))
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        app.error = "commit resolution failed: not found"

    monkeypatch.setattr(reconciler, "step", MagicMock(return_value=None))
    reconciler.tick()

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        assert app.error == "commit resolution failed: not found"
