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


def test_outbox_and_bootstrap_use_lazy_factory():
    outbox = (ROOT / "app/outbox_relay.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/init_db.py").read_text(encoding="utf-8")
    assert "from app.db import get_session_factory" in outbox
    assert "get_session_factory()()" in outbox
    assert "from app.db import get_session_factory" in bootstrap
    assert "get_session_factory().kw[\"bind\"]" in bootstrap
    assert "from app.db import engine" not in bootstrap
