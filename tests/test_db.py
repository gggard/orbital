"""Unit tests for orbital.db: lazy engine/session init and rollback-on-error."""

import pytest

from orbital import db
from orbital.config import get_settings


@pytest.fixture(autouse=True)
def _reset_db_state(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBITAL_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    get_settings.cache_clear()
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    yield
    get_settings.cache_clear()


def test_get_engine_lazily_initializes():
    assert db._engine is None
    engine = db.get_engine()
    assert engine is not None
    assert db._engine is engine


def test_session_scope_lazily_initializes():
    assert db._SessionLocal is None
    with db.session_scope() as session:
        assert session is not None
    assert db._SessionLocal is not None


def test_session_scope_rolls_back_on_exception():
    from orbital.models import App

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with db.session_scope() as session:
            session.add(App(id="x1", slug="x1", repo_url="https://x/y"))
            session.flush()
            raise Boom()

    with db.session_scope() as session:
        assert session.get(App, "x1") is None


def test_migrate_apps_table_adds_missing_columns_idempotently(tmp_path):
    """Simulates an install created before app_type/build_command/output_dir
    existed: a pre-migration `apps` table (full pre-PR column set, several
    NOT NULL with no DDL-level default - e.g. state/pending_action/
    webhook_token) with main_file/python_version still NOT NULL too.
    init_engine() must bring it up to date without violating any of those
    NOT NULL constraints on the rebuild, and a second call must be a no-op
    (SQLite path rebuilds the table, so this also guards against rebuilding
    on every startup)."""
    import sqlalchemy as sa

    url = f"sqlite:///{tmp_path}/premigration.db"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE apps (
                    id VARCHAR(12) PRIMARY KEY,
                    slug VARCHAR(63) UNIQUE NOT NULL,
                    repo_url VARCHAR(500) NOT NULL,
                    branch VARCHAR(200) NOT NULL,
                    main_file VARCHAR(500) NOT NULL,
                    python_version VARCHAR(10) NOT NULL,
                    public BOOLEAN NOT NULL,
                    allowed_groups TEXT,
                    owner_groups TEXT,
                    state VARCHAR(20) NOT NULL,
                    pending_action VARCHAR(20) NOT NULL,
                    error TEXT,
                    secrets_toml TEXT,
                    secrets_dirty BOOLEAN NOT NULL,
                    webhook_token VARCHAR(64) NOT NULL,
                    current_build_id VARCHAR(12),
                    current_image VARCHAR(500),
                    hibernate_enabled BOOLEAN NOT NULL,
                    hibernate_after_seconds INTEGER,
                    last_active_at DATETIME NOT NULL,
                    wake_requested_at DATETIME,
                    poll_enabled BOOLEAN NOT NULL,
                    poll_interval_seconds INTEGER,
                    last_polled_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO apps (
                    id, slug, repo_url, branch, main_file, python_version,
                    public, state, pending_action, secrets_dirty, webhook_token,
                    hibernate_enabled, last_active_at, poll_enabled,
                    created_at, updated_at
                ) VALUES (
                    'a1', 'demo', 'https://x/y', 'main', 'streamlit_app.py', '3.12',
                    1, 'running', 'none', 0, 'tok123',
                    1, '2026-01-01 00:00:00', 0,
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
                """
            )
        )
    engine.dispose()

    db.init_engine(url)
    inspector = sa.inspect(db.get_engine())
    columns = {c["name"]: c for c in inspector.get_columns("apps")}
    assert "app_type" in columns
    assert "build_command" in columns
    assert "output_dir" in columns
    assert columns["main_file"]["nullable"]
    assert columns["python_version"]["nullable"]

    with db.session_scope() as session:
        from orbital.models import App

        row = session.get(App, "a1")
        assert row.slug == "demo"
        assert row.app_type.value == "streamlit"  # column default applied by rebuild
        assert row.output_dir == "."

    # second call is a no-op (doesn't error, doesn't lose data)
    db.init_engine(url)
    with db.session_scope() as session:
        from orbital.models import App

        assert session.get(App, "a1").slug == "demo"
