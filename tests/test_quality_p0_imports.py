"""Import and lazy-DB regression checks for quality audit P0 findings.

These checks must not connect to PostgreSQL or initialize a DB engine.
"""
import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_application_python_file_parses():
    for path in sorted((ROOT / "app").rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_schema_and_relay_import_without_database_engine(monkeypatch):
    import sqlalchemy.ext.asyncio as sa_async

    def forbidden(*args, **kwargs):
        raise AssertionError("DB engine created during import")

    with monkeypatch.context() as patch:
        patch.setattr(sa_async, "create_async_engine", forbidden)
        import app.db
        importlib.reload(app.db)
        importlib.import_module("app.schemas")
        importlib.import_module("app.outbox_relay")
        importlib.import_module("app.init_db")
        assert app.db.get_session_factory.cache_info().currsize == 0
    importlib.reload(app.db)


def test_outbox_hold_and_bootstrap_lazy_factory():
    outbox = (ROOT / "app/outbox_relay.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/init_db.py").read_text(encoding="utf-8")
    tree = ast.parse(outbox)
    # No engine/session imports while every relay entrypoint is on HOLD.
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "app.db"
        or isinstance(node, ast.Import) and any(alias.name == "app.db" for alias in node.names)
        for node in ast.walk(tree)
    )
    for name in ("dispatch_once", "main", "_unqualified_relay_main"):
        entry = next(node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
        assert len(entry.body) == 1
        statement = entry.body[0]
        assert isinstance(statement, ast.Raise)
        assert isinstance(statement.exc, ast.Call)
        assert isinstance(statement.exc.func, ast.Name)
        assert statement.exc.func.id == "RuntimeError"
        assert len(statement.exc.args) == 1
        assert isinstance(statement.exc.args[0], ast.Constant)
        assert "disabled" in statement.exc.args[0].value.lower()
    assert "from app.db import get_session_factory" in bootstrap
    assert "get_session_factory().kw[\"bind\"]" in bootstrap
    assert "from app.db import engine" not in bootstrap


def test_poc_bootstrap_disposes_engine_without_real_database(monkeypatch):
    """Exercise POC bootstrap with fake async engine and SQLAlchemy sessionmaker."""
    import asyncio
    from types import SimpleNamespace
    import app.init_db as bootstrap

    events = []

    class FakeConnection:
        async def run_sync(self, fn):
            events.append(("run_sync", fn))

    class FakeBegin:
        async def __aenter__(self):
            events.append("begin")
            return FakeConnection()

        async def __aexit__(self, exc_type, exc, tb):
            events.append("end")

    class FakeEngine:
        def begin(self):
            return FakeBegin()

        async def dispose(self):
            events.append("dispose")

    class FakeFactory:
        kw = {"bind": FakeEngine()}

    def factory():
        events.append("factory")
        return FakeFactory()

    factory.cache_clear = lambda: events.append("clear")
    monkeypatch.setattr(bootstrap, "get_session_factory", factory)
    asyncio.run(bootstrap.main())
    assert events == [
        "factory", "begin", ("run_sync", bootstrap.Base.metadata.create_all),
        "end", "dispose", "clear",
    ]
