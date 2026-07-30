"""Recent-activity feed: the `activity.record()` helper and its hook points
in the apps API and the reconciler's build/deploy/hibernate/wake lifecycle.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from orbital import activity
from orbital.api.security import User, get_current_user
from orbital.config import get_settings
from orbital.models import App, AppState, AppType, Build, Event, PendingAction

ADMIN = User(email="carol@example.com", groups=["admins"], role="admin")


# -- activity.record() --------------------------------------------------------


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    from orbital import db as db_mod

    db_mod.init_engine(f"sqlite:///{tmp_path}/test.db")
    with db_mod.session_scope() as s:
        yield s
    get_settings.cache_clear()


def test_record_appends_an_event(session):
    activity.record(session, "my-app", "created", "info", "alice@example.com")
    events = session.scalars(select(Event)).all()
    assert len(events) == 1
    assert events[0].slug == "my-app"
    assert events[0].text == "created"
    assert events[0].level == "info"
    assert events[0].actor == "alice@example.com"


def test_record_caps_history_per_app(session, monkeypatch):
    monkeypatch.setattr(activity, "MAX_EVENTS_PER_APP", 5)
    for i in range(10):
        activity.record(session, "app", f"event {i}", "default", "reconciler")
    events = session.scalars(select(Event).where(Event.slug == "app")).all()
    assert len(events) == 5
    texts = {e.text for e in events}
    assert "event 0" not in texts
    assert "event 9" in texts


def test_record_caps_global_history_across_many_apps(session, monkeypatch):
    monkeypatch.setattr(activity, "MAX_EVENTS_PER_APP", 2)
    monkeypatch.setattr(activity, "MAX_EVENTS", 10)
    for i in range(20):
        activity.record(session, f"app-{i}", "created", "info", "dev@localhost")
    events = session.scalars(select(Event)).all()
    assert len(events) == 10
    # the most recently-created apps' events are the ones kept
    slugs = {e.slug for e in events}
    assert "app-19" in slugs
    assert "app-0" not in slugs


def test_record_survives_a_noisy_neighbor(session, monkeypatch):
    """Regression: a single app hammering the feed (a flapping build loop,
    aggressive git polling…) must not be able to evict another app's
    history just by generating enough volume - each slug is capped to its
    own floor on every write, so its own row count never grows large enough
    to threaten the global cap.
    """
    monkeypatch.setattr(activity, "MAX_EVENTS_PER_APP", 5)
    monkeypatch.setattr(activity, "MAX_EVENTS", 50)
    activity.record(session, "quiet-app", "created", "info", "alice@example.com")
    for i in range(200):
        activity.record(session, "noisy-app", f"build started {i}", "warning", "reconciler")
    quiet_events = session.scalars(select(Event).where(Event.slug == "quiet-app")).all()
    assert len(quiet_events) == 1
    assert quiet_events[0].text == "created"
    noisy_events = session.scalars(select(Event).where(Event.slug == "noisy-app")).all()
    assert len(noisy_events) == 5


# -- API hooks: create/delete/deploy/reboot -----------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ORBITAL_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("ORBITAL_UI_AUTH_ENABLED", "true")
    monkeypatch.setenv("ORBITAL_SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("ORBITAL_ADMIN_GROUPS", '["admins"]')
    get_settings.cache_clear()
    from orbital import db
    from orbital.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        c.app = app
        c.app.dependency_overrides[get_current_user] = lambda: ADMIN
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def make_app(client, slug="app1"):
    return client.post("/api/v1/apps", json={"slug": slug, "repo_url": "https://github.com/x/y"})


def test_create_app_records_a_created_event(client):
    make_app(client, "sales-dash")
    body = client.get("/api/v1/admin/activity").json()
    assert any(e["slug"] == "sales-dash" and e["text"] == "created" for e in body)
    created = next(e for e in body if e["slug"] == "sales-dash")
    assert created["actor"] == ADMIN.email
    assert created["level"] == "info"


def test_delete_app_records_a_delete_requested_event(client):
    app_id = make_app(client, "throwaway").json()["id"]
    client.delete(f"/api/v1/apps/{app_id}")
    body = client.get("/api/v1/admin/activity").json()
    assert any(e["slug"] == "throwaway" and e["text"] == "delete requested" for e in body)


def test_deploy_sets_requested_by_without_logging_yet(client):
    app_id = make_app(client, "demo").json()["id"]

    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        app.state = AppState.running
        app.requested_by = None

    client.post(f"/api/v1/apps/{app_id}/deploy")
    with db_mod.session_scope() as session:
        assert session.get(App, app_id).requested_by == ADMIN.email


def test_reboot_sets_requested_by(client):
    app_id = make_app(client, "demo").json()["id"]
    from orbital import db as db_mod

    with db_mod.session_scope() as session:
        app = session.get(App, app_id)
        app.state = AppState.running

    client.post(f"/api/v1/apps/{app_id}/reboot")
    with db_mod.session_scope() as session:
        assert session.get(App, app_id).requested_by == ADMIN.email


def test_activity_endpoint_requires_admin(client):
    from orbital.api.security import User as _User

    client.app.dependency_overrides[get_current_user] = lambda: _User(
        email="v@example.com", groups=[], role="viewer"
    )
    assert client.get("/api/v1/admin/activity").status_code == 403


def test_activity_endpoint_orders_newest_first(client):
    make_app(client, "one")
    make_app(client, "two")
    body = client.get("/api/v1/admin/activity").json()
    slugs = [e["slug"] for e in body]
    assert slugs.index("two") < slugs.index("one")


# -- reconciler hooks: build/deploy/hibernate/wake ----------------------------


def make_reconciler_app(
    state=AppState.building,
    current_build_id="bld000000001",
    requested_by=None,
) -> App:
    return App(
        id="abc123def456",
        slug="demo",
        repo_url="https://github.com/x/y",
        branch="main",
        app_type=AppType.streamlit,
        main_file="streamlit_app.py",
        python_version="3.12",
        state=state,
        owner_groups=[],
        allowed_groups=[],
        pending_action=PendingAction.none,
        current_build_id=current_build_id,
        requested_by=requested_by,
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


def _events(session, slug=None):
    stmt = select(Event).order_by(Event.created_at)
    if slug is not None:
        stmt = stmt.where(Event.slug == slug)
    return session.scalars(stmt).all()


def test_start_build_records_build_started_attributed_to_requester(reconciler, monkeypatch):
    monkeypatch.setattr(
        "orbital.k8s.reconciler.resolve_branch_head", lambda url, branch: "a" * 40
    )
    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.created, requested_by="alice@example.com")
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._start_build(session, a)
        events = _events(session, "demo")
        assert events[-1].text == "build started"
        assert events[-1].actor == "alice@example.com"


def test_start_build_falls_back_to_reconciler_actor(reconciler, monkeypatch):
    monkeypatch.setattr(
        "orbital.k8s.reconciler.resolve_branch_head", lambda url, branch: "a" * 40
    )
    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.created, requested_by=None)
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._start_build(session, a)
        events = _events(session, "demo")
        assert events[-1].actor == "reconciler"


def test_start_build_git_error_records_build_failed(reconciler, monkeypatch):
    from orbital.gitutil import GitError

    def _raise(url, branch):
        raise GitError("not found")

    monkeypatch.setattr("orbital.k8s.reconciler.resolve_branch_head", _raise)
    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.created, requested_by="bob@example.com")
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._start_build(session, a)
        assert a.requested_by is None
        events = _events(session, "demo")
        assert events[-1].text == "build failed"
        assert events[-1].actor == "bob@example.com"


def _job(conditions=None, succeeded=None, failed=None):
    return SimpleNamespace(
        status=SimpleNamespace(conditions=conditions, succeeded=succeeded, failed=failed)
    )


def test_check_build_failure_records_event_and_clears_requested_by(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client

    batch = MagicMock()
    batch.read_namespaced_job.return_value = _job(
        conditions=[SimpleNamespace(type="Failed", status="True", message="boom")]
    )
    monkeypatch.setattr(k8s_client, "batch", lambda: batch)

    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.building, requested_by="alice@example.com")
    build = Build(id="bld000000001", app_id=app.id, commit_sha="a" * 40, image="img")
    with db_mod.session_scope() as session:
        session.add(app)
        session.add(build)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._check_build(session, a)
        assert a.requested_by is None
        events = _events(session, "demo")
        assert events[-1].text == "build failed"
        assert events[-1].actor == "alice@example.com"


def test_check_rollout_success_records_redeployed_event(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client

    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment.return_value = SimpleNamespace(
        status=SimpleNamespace(ready_replicas=1, updated_replicas=1)
    )
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)

    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.deploying, requested_by="alice@example.com")
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._check_rollout(session, a)
        assert a.state == AppState.running
        assert a.requested_by is None
        events = _events(session, "demo")
        assert events[-1].text == "redeployed successfully"
        assert events[-1].level == "success"
        assert events[-1].actor == "alice@example.com"


def test_check_rollout_crash_loop_records_deploy_failed_event(reconciler, monkeypatch):
    from orbital.k8s import client as k8s_client

    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment.return_value = SimpleNamespace(
        status=SimpleNamespace(ready_replicas=0, updated_replicas=0)
    )
    core = MagicMock()
    pod = SimpleNamespace(
        status=SimpleNamespace(
            container_statuses=[
                SimpleNamespace(
                    state=SimpleNamespace(
                        waiting=SimpleNamespace(reason="CrashLoopBackOff", message="boom")
                    )
                )
            ]
        )
    )
    core.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: apps_v1)
    monkeypatch.setattr(k8s_client, "core", lambda: core)

    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.deploying, requested_by=None)
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._check_rollout(session, a)
        assert a.state == AppState.deploy_failed
        events = _events(session, "demo")
        assert events[-1].text == "deploy failed"
        assert events[-1].actor == "reconciler"


def test_maybe_hibernate_records_sleep_event(reconciler, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from kubernetes.client import ApiException

    from orbital.k8s import client as k8s_client

    networking = MagicMock()
    networking.read_namespaced_ingress.side_effect = ApiException(status=404)
    monkeypatch.setattr(k8s_client, "networking", lambda: networking)
    monkeypatch.setattr(k8s_client, "apps_v1", lambda: MagicMock())

    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.running)
    app.hibernate_enabled = True
    app.last_active_at = datetime.now(UTC) - timedelta(hours=13)
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._maybe_hibernate(session, a)
        assert a.state == AppState.sleeping
        events = _events(session, "demo")
        assert "went to sleep" in events[-1].text
        assert events[-1].actor == "reconciler"


def test_maybe_wake_records_wake_event(reconciler, monkeypatch):
    from datetime import UTC, datetime

    from orbital.k8s import client as k8s_client

    monkeypatch.setattr(k8s_client, "apps_v1", lambda: MagicMock())

    from orbital import db as db_mod

    app = make_reconciler_app(state=AppState.sleeping)
    app.wake_requested_at = datetime.now(UTC)
    with db_mod.session_scope() as session:
        session.add(app)

    with db_mod.session_scope() as session:
        a = session.get(App, "abc123def456")
        reconciler._maybe_wake(session, a)
        assert a.state == AppState.deploying
        events = _events(session, "demo")
        assert events[-1].text == "woke up"
        assert events[-1].actor == "reconciler"
