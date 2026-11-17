"""The API must be importable without initializing a PostgreSQL engine."""
import importlib


def test_database_engine_not_initialized_during_import(monkeypatch):
    import sqlalchemy.ext.asyncio as sa_async

    def fail_if_called(*args, **kwargs):
        raise AssertionError("database engine initialized during import")

    with monkeypatch.context() as patch:
        patch.setattr(sa_async, "create_async_engine", fail_if_called)
        import app.db
        importlib.reload(app.db)
        assert app.db.get_session_factory.cache_info().currsize == 0
    importlib.reload(app.db)


def test_database_session_factory_is_lazy_and_cached(monkeypatch):
    import app.db

    class FakeFactory:
        pass

    calls = []

    def fake_engine(url, **kwargs):
        calls.append((url, kwargs))
        return object()

    def fake_maker(engine, **kwargs):
        return FakeFactory()

    with monkeypatch.context() as patch:
        from types import SimpleNamespace
        patch.setattr(app.db, "settings", SimpleNamespace(database_url="postgresql+asyncpg://localhost/test"))
        patch.setattr(app.db, "create_async_engine", fake_engine)
        patch.setattr(app.db, "async_sessionmaker", fake_maker)
        app.db.get_session_factory.cache_clear()
        assert app.db.get_session_factory() is app.db.get_session_factory()
        assert len(calls) == 1
    app.db.get_session_factory.cache_clear()


def test_db_module_import_in_fresh_interpreter_without_engine():
    """A fresh process catches import-time engine creation hidden by pytest caches."""
    import subprocess
    import sys
    from pathlib import Path

    script = """
import sqlalchemy.ext.asyncio as sa_async

def forbid_engine(*args, **kwargs):
    raise AssertionError("engine created at import time")

sa_async.create_async_engine = forbid_engine
from app.db import get_session_factory
assert get_session_factory.cache_info().currsize == 0
print("lazy database import OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
