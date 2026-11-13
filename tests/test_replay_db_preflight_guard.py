"""Static safety regression checks for opt-in replay PostgreSQL tests.

These run without a database and prevent Python -O from silently disabling
the fixture's database identity checks.
"""
import ast
import io
import tokenize
from pathlib import Path

import pytest


def test_replay_db_preflight_never_uses_python_assert():
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    fixtures = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    if any(isinstance(node, ast.Assert) for node in ast.walk(fixture)):
        pytest.fail("Database write preconditions must not rely on assertions disabled by -O")


def test_replay_db_preflight_checks_actual_server_before_yield():
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    fixtures = [
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    yield_nodes = [
        node for node in ast.walk(fixture) if isinstance(node, ast.Yield)
    ]
    if len(yield_nodes) != 1:
        pytest.fail("Replay DB fixture must yield exactly once")
    before_yield = source.splitlines()[:yield_nodes[0].lineno - 1]
    fixture_source = "\n".join(
        before_yield[fixture.lineno - 1:]
    )
    # Comments cannot establish a safety precondition.
    fixture_source = tokenize.untokenize(
        token for token in tokenize.generate_tokens(
            io.StringIO(fixture_source).readline
        ) if token.type != tokenize.COMMENT
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
        if required not in fixture_source:
            pytest.fail(f"Replay DB preflight missing before yield: {required}")
