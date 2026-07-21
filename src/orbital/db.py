from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine = None
_SessionLocal: sessionmaker | None = None


def init_engine(database_url: str | None = None):
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    from . import models

    models.Base.metadata.create_all(_engine)
    _migrate_apps_table(_engine, models)
    return _engine


# Columns added to `apps` after its initial release, as (name, DDL type,
# SQL literal default). The DDL type carries its own DEFAULT for `ALTER
# TABLE ... ADD COLUMN` (postgres); the literal is used again for the
# SQLite rebuild path below, where a raw `INSERT SELECT` bypasses
# mapped_column's Python-side `default=` entirely (that's ORM-insert-time
# only, not a DDL-level DEFAULT) and would otherwise violate NOT NULL on
# any column not already present in the old table.
_APPS_NEW_COLUMNS = [
    ("app_type", "VARCHAR(20) NOT NULL DEFAULT 'streamlit'", "'streamlit'"),
    ("build_command", "VARCHAR(500)", None),
    ("output_dir", "VARCHAR(500) NOT NULL DEFAULT '.'", "'.'"),
]
# Columns that used to be NOT NULL (streamlit-only fields, now optional so
# static apps can leave them unset).
_APPS_NOW_NULLABLE = ("main_file", "python_version")


def _migrate_apps_table(engine, models) -> None:
    """Idempotently bring an existing `apps` table up to date with the
    current model. Safe to call on every startup: each check is a no-op if
    already applied.
    """
    inspector = inspect(engine)
    if "apps" not in inspector.get_table_names():
        return  # fresh DB - create_all just built the current schema

    columns = {col["name"]: col for col in inspector.get_columns("apps")}
    missing = [(name, ddl) for name, ddl, _ in _APPS_NEW_COLUMNS if name not in columns]
    still_not_null = [
        name for name in _APPS_NOW_NULLABLE if not columns.get(name, {}).get("nullable", True)
    ]
    if not missing and not still_not_null:
        return

    if engine.dialect.name == "sqlite":
        # SQLite has no ALTER COLUMN to add/drop NOT NULL, so rebuild the
        # table against the current model definition and copy the data over.
        _sqlite_rebuild_apps_table(engine, models, list(columns))
        return

    with engine.begin() as conn:
        for name, ddl in missing:
            conn.execute(text(f"ALTER TABLE apps ADD COLUMN {name} {ddl}"))
        for name in still_not_null:
            conn.execute(text(f"ALTER TABLE apps ALTER COLUMN {name} DROP NOT NULL"))


def _sqlite_rebuild_apps_table(engine, models, old_columns: list[str]) -> None:
    apps_table = models.App.__table__
    common = [c for c in old_columns if c in apps_table.columns]
    # Columns new to this table that aren't in the old data need an explicit
    # literal in the SELECT list (see _APPS_NEW_COLUMNS docstring above) -
    # nullable ones (build_command) are fine left out entirely (-> NULL).
    extra = [
        (name, literal)
        for name, _, literal in _APPS_NEW_COLUMNS
        if name not in common and literal is not None
    ]
    insert_cols = ", ".join([*common, *(name for name, _ in extra)])
    select_cols = ", ".join([*common, *(literal for _, literal in extra)])
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE apps RENAME TO apps_old"))
        apps_table.create(conn)
        conn.execute(
            text(f"INSERT INTO apps ({insert_cols}) SELECT {select_cols} FROM apps_old")
        )
        conn.execute(text("DROP TABLE apps_old"))


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session
