"""Static safety regression checks for opt-in replay PostgreSQL tests.

These run without a database and prevent Python -O from silently disabling
the fixture's database identity checks.
"""
import ast
from pathlib import Path


def test_replay_db_preflight_never_uses_python_assert():
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    fixtures = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    assert len(fixtures) == 1
    fixture = fixtures[0]
    assert not [
        node for node in ast.walk(fixture) if isinstance(node, ast.Assert)
    ], "Database write preconditions must not rely on assertions disabled by -O"


def test_replay_db_preflight_checks_actual_server_before_yield():
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    fixture = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    )
    yield_nodes = [
        node for node in ast.walk(fixture) if isinstance(node, ast.Yield)
    ]
    assert len(yield_nodes) == 1
    before_yield = source.splitlines()[:yield_nodes[0].lineno - 1]
    fixture_source = "\n".join(
        before_yield[fixture.lineno - 1:]
    )
    for required in (
        "GAMMA_REPLAY_TEST_ALLOW_WRITE",
        "current_database()",
        "server_version_num",
        "inet_server_addr()",
        "gateway_assertion_replay",
        "alembic_version",
        "0002_gateway_replay",
    ):
        assert required in fixture_source, required
