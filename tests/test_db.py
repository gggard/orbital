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


def _create_premigration_db(url: str) -> None:
    """A pre-PR `apps` table (full pre-PR column set, several NOT NULL with
    no DDL-level default - e.g. state/pending_action/webhook_token) with
    main_file/python_version still NOT NULL too. Crucially, `slug`'s unique
    constraint is a separately named index (`ix_apps_slug`), matching what
    SQLAlchemy's `mapped_column(unique=True, index=True)` actually generates
    - an inline `UNIQUE` column constraint instead would create an unnamed
    SQLite auto-index and silently fail to reproduce the real-world bug this
    guards against (see test_migrate_apps_table_survives_index_name_collision).
    """
    import sqlalchemy as sa

    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE apps (
                    id VARCHAR(12) PRIMARY KEY,
                    slug VARCHAR(63) NOT NULL,
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
        conn.execute(sa.text("CREATE UNIQUE INDEX ix_apps_slug ON apps (slug)"))
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


def test_migrate_apps_table_adds_missing_columns_idempotently(tmp_path):
    """init_engine() must bring a pre-migration DB up to date without
    violating any NOT NULL constraints on the rebuild, and a second call
    must be a no-op (SQLite path rebuilds the table, so this also guards
    against rebuilding on every startup)."""
    import sqlalchemy as sa

    url = f"sqlite:///{tmp_path}/premigration.db"
    _create_premigration_db(url)

    db.init_engine(url)
    inspector = sa.inspect(db.get_engine())
    columns = {c["name"]: c for c in inspector.get_columns("apps")}
    assert "app_type" in columns
    assert "build_command" in columns
    assert "output_dir" in columns
    assert "tags" in columns
    assert "last_scan_id" in columns
    assert "scan_requested_at" in columns
    assert columns["main_file"]["nullable"]
    assert columns["python_version"]["nullable"]

    with db.session_scope() as session:
        from orbital.models import App

        row = session.get(App, "a1")
        assert row.slug == "demo"
        assert row.app_type.value == "streamlit"  # column default applied by rebuild
        assert row.output_dir == "."
        assert row.tags == []

    # second call is a no-op (doesn't error, doesn't lose data)
    db.init_engine(url)
    with db.session_scope() as session:
        from orbital.models import App

        assert session.get(App, "a1").slug == "demo"


def test_migrate_apps_table_survives_index_name_collision(tmp_path):
    """Regression test: SQLite's index namespace is database-wide, so
    `ALTER TABLE apps RENAME TO apps_old` does NOT rename `ix_apps_slug`
    along with it - the new `apps` table (which defines the same index
    name) collided with the still-there old one and crashed startup with
    every existing row intact-but-unreachable in `apps_old` (caught against
    a real pre-existing dev database, not just this synthetic repro)."""
    url = f"sqlite:///{tmp_path}/premigration.db"
    _create_premigration_db(url)

    db.init_engine(url)  # must not raise

    with db.session_scope() as session:
        from orbital.models import App

        assert session.get(App, "a1").slug == "demo"


def test_migrate_apps_table_recovers_from_partial_previous_failure(tmp_path):
    """Simulates a crash partway through a previous SQLite rebuild attempt:
    `apps_old` (the real data) and a partial, empty `apps` (current schema,
    created but never populated) both present - exactly what
    `_sqlite_rebuild_apps_table` left behind before the index-collision fix,
    since SQLite auto-commits each DDL statement individually rather than
    the whole rebuild being one atomic transaction. init_engine() must
    discard the partial `apps` and recover the real data from `apps_old`."""
    import sqlalchemy as sa

    from orbital import models

    url = f"sqlite:///{tmp_path}/partial.db"
    _create_premigration_db(url)

    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE apps RENAME TO apps_old"))
        conn.execute(sa.text("DROP INDEX ix_apps_slug"))
        # partial: current schema, no data - as if the process died between
        # this CREATE TABLE succeeding and the row-copying INSERT running
        models.App.__table__.create(conn)
    engine.dispose()

    db.init_engine(url)  # must not raise, must not silently keep 0 rows

    inspector = sa.inspect(db.get_engine())
    assert "apps_old" not in inspector.get_table_names()
    with db.session_scope() as session:
        from orbital.models import App

        assert session.get(App, "a1").slug == "demo"
