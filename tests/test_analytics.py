"""Analytics: view recording (dedup, identity) and aggregation (SPEC §4.7)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from streamlit_host import analytics
from streamlit_host.api.security import User, get_current_user
from streamlit_host.config import get_settings
from streamlit_host.models import App, ViewEvent

ADMIN = User(email="carol@example.com", groups=["admins"], role="admin")
CREATOR = User(email="alice@example.com", groups=["data-team"], role="creator")
OUTSIDER = User(email="bob@example.com", groups=["other-team"], role="creator")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SH_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("SH_RECONCILER_ENABLED", "false")
    monkeypatch.setenv("SH_AUTH_ENABLED", "true")
    monkeypatch.setenv("SH_OAUTH2_PROXY_AUTH_URL", "http://oauth2-proxy.test/oauth2/auth")
    monkeypatch.setenv("SH_UI_AUTH_ENABLED", "false")
    monkeypatch.setenv("SH_APPS_DOMAIN", "apps.local")
    get_settings.cache_clear()
    from streamlit_host import db
    from streamlit_host.main import app

    db.init_engine(f"sqlite:///{tmp_path}/test.db")
    with TestClient(app) as c:
        c.app = app
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def as_user(client, user: User):
    client.app.dependency_overrides[get_current_user] = lambda: user


def make_client_app(client, slug="demo", **extra):
    r = client.post(
        "/api/v1/apps",
        json={"slug": slug, "repo_url": "https://github.com/x/y", "branch": "main", **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# -- analytics.record_view: dedup ------------------------------------------


def test_record_view_dedupes_within_window():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        analytics.record_view(session, app, viewer=None, viewer_key="1.2.3.4")
        analytics.record_view(session, app, viewer=None, viewer_key="1.2.3.4")
        session.flush()
        assert session.query(ViewEvent).filter_by(app_id="app1").count() == 1


def test_record_view_distinct_keys_both_recorded():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        analytics.record_view(session, app, viewer=None, viewer_key="1.2.3.4")
        analytics.record_view(session, app, viewer=None, viewer_key="5.6.7.8")
        session.flush()
        assert session.query(ViewEvent).filter_by(app_id="app1").count() == 2


def test_record_view_outside_window_counted_again():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        old = datetime.now(UTC) - analytics.DEDUPE_WINDOW - timedelta(minutes=1)
        session.add(ViewEvent(app_id="app1", viewer=None, viewer_key="1.2.3.4", viewed_at=old))
        session.flush()
        analytics.record_view(session, app, viewer=None, viewer_key="1.2.3.4")
        session.flush()
        assert session.query(ViewEvent).filter_by(app_id="app1").count() == 2


def test_record_view_blank_key_ignored():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        analytics.record_view(session, app, viewer=None, viewer_key="")
        session.flush()
        assert session.query(ViewEvent).filter_by(app_id="app1").count() == 0


# -- analytics.summary: aggregation -----------------------------------------


def test_summary_aggregates_totals_and_daily_series():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        now = datetime.now(UTC)
        session.add_all(
            [
                ViewEvent(app_id="app1", viewer="a@x.com", viewer_key="a@x.com", viewed_at=now),
                ViewEvent(app_id="app1", viewer="b@x.com", viewer_key="b@x.com", viewed_at=now),
                ViewEvent(
                    app_id="app1",
                    viewer=None,
                    viewer_key="9.9.9.9",
                    viewed_at=now - timedelta(days=2),
                ),
            ]
        )
        session.flush()

        result = analytics.summary(session, app)
        assert result.total_views == 3
        assert result.unique_viewers_1d == 2
        assert result.unique_viewers_7d == 3
        assert result.unique_viewers_30d == 3
        assert result.last_viewed_at is not None
        assert len(result.daily) == 2  # two distinct days
        assert {v.viewer for v in result.viewers} == {"a@x.com", "b@x.com"}
        # anonymous public view never surfaces as a named viewer
        assert "9.9.9.9" not in {v.viewer for v in result.viewers}


def test_summary_empty_app_has_zeroed_stats():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        result = analytics.summary(session, app)
        assert result.total_views == 0
        assert result.last_viewed_at is None
        assert result.daily == []
        assert result.viewers == []


# -- recording via the real beacon endpoints ---------------------------------


def test_public_activity_ping_records_anonymous_view(client):
    app_id = make_client_app(client, public=True)
    assert client.get(f"/activity/{app_id}").status_code == 200

    as_user(client, ADMIN)
    body = client.get(f"/api/v1/apps/{app_id}/analytics").json()
    assert body["total_views"] == 1
    assert body["unique_viewers_1d"] == 1
    assert body["viewers"] == []  # anonymous - no identity to show


def test_repeated_public_pings_dedupe_to_one_view(client):
    app_id = make_client_app(client, public=True)
    for _ in range(5):
        client.get(f"/activity/{app_id}")

    as_user(client, ADMIN)
    body = client.get(f"/api/v1/apps/{app_id}/analytics").json()
    assert body["total_views"] == 1


def test_private_authz_records_named_viewer(client, monkeypatch):
    from streamlit_host.api import authz

    monkeypatch.setattr(
        authz, "check_session", lambda url, cookie: (True, "alice@example.com", ["data-team"])
    )
    app_id = make_client_app(client, public=False, allowed_groups=["data-team"])
    assert client.get(f"/authz/{app_id}").status_code == 200

    as_user(client, ADMIN)
    body = client.get(f"/api/v1/apps/{app_id}/analytics").json()
    assert body["total_views"] == 1
    assert [v["viewer"] for v in body["viewers"]] == ["alice@example.com"]


def test_private_authz_denied_group_records_no_view(client, monkeypatch):
    from streamlit_host.api import authz

    monkeypatch.setattr(
        authz, "check_session", lambda url, cookie: (True, "bob@example.com", ["other"])
    )
    app_id = make_client_app(client, public=False, allowed_groups=["data-team"])
    assert client.get(f"/authz/{app_id}").status_code == 403

    as_user(client, ADMIN)
    body = client.get(f"/api/v1/apps/{app_id}/analytics").json()
    assert body["total_views"] == 0


# -- visibility (SPEC FR-7.3: owner(s) and Admins) ---------------------------


def test_analytics_visible_to_owning_group_and_admin(client):
    as_user(client, CREATOR)
    app_id = make_client_app(client, owner_groups=["data-team"])

    assert client.get(f"/api/v1/apps/{app_id}/analytics").status_code == 200

    as_user(client, ADMIN)
    assert client.get(f"/api/v1/apps/{app_id}/analytics").status_code == 200


def test_analytics_hidden_from_non_owning_group(client):
    as_user(client, CREATOR)
    app_id = make_client_app(client, owner_groups=["data-team"])

    as_user(client, OUTSIDER)
    assert client.get(f"/api/v1/apps/{app_id}/analytics").status_code == 404


# -- deletion cascades (SPEC FR-5.3) -----------------------------------------


def test_deleting_app_removes_view_events():
    from streamlit_host import db as db_mod

    db_mod.init_engine("sqlite://")
    with db_mod.session_scope() as session:
        app = App(id="app1", slug="app1", repo_url="https://x/y", owner_groups=[])
        session.add(app)
        session.flush()
        session.add(ViewEvent(app_id="app1", viewer=None, viewer_key="1.2.3.4"))
        session.flush()

    with db_mod.session_scope() as session:
        app = session.get(App, "app1")
        session.delete(app)

    with db_mod.session_scope() as session:
        assert session.query(ViewEvent).filter_by(app_id="app1").count() == 0
