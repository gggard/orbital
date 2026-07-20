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
