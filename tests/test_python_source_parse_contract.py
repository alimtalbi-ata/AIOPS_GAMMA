"""Compile every checked-in Python source without imports, DB, or network.

This catches malformed source such as literal backslash-n sequences accidentally
written into a test module. It does not execute tests or prove runtime safety.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("app", "tests", "migrations", "scripts")


def test_all_python_sources_parse_without_imports():
    sources = sorted(
        path for directory in SOURCE_DIRS
        for path in (ROOT / directory).rglob("*.py")
        if path.is_file()
    )
    assert sources, "No Python source files discovered"
    failures = []
    for path in sources:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeError) as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    assert not failures, "Invalid Python source:\n" + "\n".join(failures)


def test_postgres_tenant_isolation_assertions_require_positive_exact_rows():
    source = (ROOT / "tests" / "test_resource_list_http_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    test = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_foreign_rows_and_foreign_incident_are_not_serialized"
    )
    exact_assertions = [
        node for node in ast.walk(test)
        if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "values"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Name)
        and node.test.comparators[0].id == "expected"
    ]
    assert exact_assertions, "Isolation test must assert exact positive tenant-owned rows"

def test_disposable_postgres_preflight_never_uses_optimizable_assertions():
    """A Python -O invocation must not remove pre-write safety checks."""
    source = (ROOT / "tests" / "test_resource_list_http_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    fixture = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "tenant_postgres"
    )
    prepare = next(
        node for node in fixture.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare"
    )
    preflight = []
    for statement in prepare.body:
        if isinstance(statement, ast.AsyncWith):
            preflight = statement.body
            break
    assert preflight, "Missing connected-server pre-write checks"
    # Every check in prepare() preceding the first session.add_all() is a
    # safety gate. A nested assert anywhere in that region is stripped by -O.
    assert not any(isinstance(node, ast.Assert)
                   for node in ast.walk(prepare)), (
        "PostgreSQL prepare must use pytest.fail, not optimizable assert"
    )
    preflight_source = "\n".join(ast.unparse(node) for node in preflight)
    for required in (
        "current_database()", "inet_server_addr()", "rolsuper",
        "server_version_num", "alembic_version", "to_regclass",
        "SELECT count(*)", "pytest.fail",
    ):
        assert required in preflight_source

def test_source_parser_detects_invalid_python_in_disposable_tree(tmp_path, monkeypatch):
    """Exercise the real source guard, including its failure path."""
    import sys

    module = sys.modules[__name__]
    directory = tmp_path / "app"
    directory.mkdir()
    (directory / "broken.py").write_text("x = 1\n    if True:\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import pytest

    with pytest.raises(AssertionError, match="Invalid Python source"):
        test_all_python_sources_parse_without_imports()


def test_source_parser_accepts_valid_python_in_disposable_tree(tmp_path, monkeypatch):
    """The parser must not reject ordinary valid source files."""
    import sys

    module = sys.modules[__name__]
    directory = tmp_path / "app"
    directory.mkdir()
    (directory / "valid.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    test_all_python_sources_parse_without_imports()

def test_source_parser_rejects_missing_sources(tmp_path, monkeypatch):
    """A missing checkout must not be reported as a clean syntax scan."""
    import sys
    import pytest

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="No Python source files discovered"):
        test_all_python_sources_parse_without_imports()

def test_exact_row_guard_rejects_inert_comparison(tmp_path, monkeypatch):
    """A comparison expression alone cannot prove tenant isolation."""
    import sys
    import pytest

    source = tmp_path / "tests" / "test_resource_list_http_postgres.py"
    source.parent.mkdir()
    source.write_text(
        "def test_foreign_rows_and_foreign_incident_are_not_serialized():\n"
        "    values = []\n"
        "    expected = ['tenant-a-service']\n"
        "    values == expected\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises(AssertionError, match="must assert exact"):
        test_postgres_tenant_isolation_assertions_require_positive_exact_rows()


def test_exact_row_guard_accepts_real_assertion(tmp_path, monkeypatch):
    """An executable exact equality assertion satisfies the static contract."""
    import sys

    source = tmp_path / "tests" / "test_resource_list_http_postgres.py"
    source.parent.mkdir()
    source.write_text(
        "def test_foreign_rows_and_foreign_incident_are_not_serialized():\n"
        "    values = []\n"
        "    expected = ['tenant-a-service']\n"
        "    assert values == expected\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    test_postgres_tenant_isolation_assertions_require_positive_exact_rows()
