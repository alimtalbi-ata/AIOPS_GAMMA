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
