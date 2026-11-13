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
    comparisons = [
        node for node in ast.walk(test)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "values"
        and any(isinstance(op, ast.Eq) for op in node.ops)
        and any(isinstance(item, ast.Name) and item.id == "expected"
                for item in node.comparators)
    ]
    assert comparisons, "Isolation test must require exact positive tenant-owned rows"
