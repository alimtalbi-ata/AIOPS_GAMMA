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

def test_replay_db_refuses_optimized_python_before_connection():
    """Prevent -O from eliding assert expressions that perform DB operations."""
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
    first = fixture.body[0] if fixture.body else None
    if not isinstance(first, ast.If):
        pytest.fail("Replay DB fixture must reject -O before database setup")
    if not isinstance(first.test, ast.UnaryOp) or not isinstance(first.test.op, ast.Not):
        pytest.fail("Replay DB fixture must check not __debug__")
    if not isinstance(first.test.operand, ast.Name) or first.test.operand.id != "__debug__":
        pytest.fail("Replay DB fixture must check not __debug__")
    if not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
        and node.func.attr == "fail"
        for statement in first.body for node in ast.walk(statement)
    ):
        pytest.fail("Optimized Python must fail before any DB access")

def test_replay_db_rejects_non_loopback_server_before_yield():
    """A dead if False branch must not count as a loopback safety check."""
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
    yields = [node for node in ast.walk(fixture) if isinstance(node, ast.Yield)]
    if len(yields) != 1:
        pytest.fail("Expected exactly one session yield")

    def is_rejection(node):
        if not isinstance(node, ast.If) or node.lineno >= yields[0].lineno:
            return False
        condition = node.test
        if not (
            isinstance(condition, ast.Compare)
            and isinstance(condition.left, ast.Name)
            and condition.left.id == "is_loopback"
            and len(condition.ops) == 1
            and isinstance(condition.ops[0], ast.IsNot)
            and len(condition.comparators) == 1
            and isinstance(condition.comparators[0], ast.Constant)
            and condition.comparators[0].value is True
        ):
            return False
        return any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "pytest"
            and call.func.attr == "fail"
            for stmt in node.body for call in ast.walk(stmt)
        )

    if not any(is_rejection(node) for node in ast.walk(fixture)):
        pytest.fail("Missing effective non-loopback rejection before session yield")

def test_loopback_decision_comes_from_database_query():
    """Reject a hardcoded True that bypasses the real server address check."""
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
    assignments = [
        node for node in ast.walk(fixture)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "is_loopback"
                for target in node.targets)
    ]
    if len(assignments) != 1:
        pytest.fail("Loopback decision must have exactly one assignment")
    value = assignments[0].value
    if not (
        isinstance(value, ast.Await)
        and isinstance(value.value, ast.Call)
        and isinstance(value.value.func, ast.Attribute)
        and value.value.func.attr == "scalar"
        and isinstance(value.value.func.value, ast.Name)
        and value.value.func.value.id == "connection"
        and len(value.value.args) == 1
        and isinstance(value.value.args[0], ast.Call)
        and isinstance(value.value.args[0].func, ast.Name)
        and value.value.args[0].func.id == "text"
        and value.value.args[0].args
        and "inet_server_addr()" in ast.unparse(value.value.args[0].args[0])
    ):
        pytest.fail("Loopback decision must await connection.scalar of server address SQL")


def test_replay_db_sql_qualification_guards_are_bound_before_yield():
    """Ensure five SQL qualifications reject unsafe results before yielding sessions."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [n for n in ast.parse(source).body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    yields = [n for n in ast.walk(fixture) if isinstance(n, (ast.Yield, ast.YieldFrom))]
    if len(yields) != 1:
        pytest.fail("Expected exactly one session yield")
    cutoff = yields[0].lineno
    checks = {
        "db_name": ("current_database()", "not db_name or not db_name.endswith('_replay_test')"),
        "server_version": ("server_version_num", "server_version is None or int(server_version) // 10000 != 16"),
        "is_loopback": ("inet_server_addr()", "is_loopback is not True"),
        "present": ("gateway_assertion_replay", "present is None"),
        "revision": ("alembic_version", "revision != '0002_gateway_replay'"),
    }
    for variable, (sql_fragment, rejection) in checks.items():
        assignments = [n for n in ast.walk(fixture) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets)]
        if len(assignments) != 1:
            pytest.fail(f"{variable}: expected one SQL assignment")
        assignment = assignments[0]
        value = assignment.value
        if not (assignment.lineno < cutoff and isinstance(value, ast.Await)
                and isinstance(value.value, ast.Call)
                and isinstance(value.value.func, ast.Attribute)
                and isinstance(value.value.func.value, ast.Name)
                and value.value.func.value.id == "connection"
                and value.value.func.attr == "scalar" and len(value.value.args) == 1):
            pytest.fail(f"{variable}: expected awaited connection.scalar before yield")
        query = value.value.args[0]
        if not (isinstance(query, ast.Call) and isinstance(query.func, ast.Name)
                and query.func.id == "text" and len(query.args) == 1
                and isinstance(query.args[0], ast.Constant)
                and isinstance(query.args[0].value, str)
                and sql_fragment in query.args[0].value):
            pytest.fail(f"{variable}: expected literal SQL query")
        expected_condition = ast.dump(ast.parse(rejection, mode="eval").body)
        guards = [n for n in ast.walk(fixture) if isinstance(n, ast.If)
                  and assignment.end_lineno < n.lineno < cutoff
                  and ast.dump(n.test) == expected_condition]
        if len(guards) != 1:
            pytest.fail(f"{variable}: missing exact rejection guard after SQL and before yield")
        guard = guards[0]
        if not any(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                   and isinstance(stmt.value.func, ast.Attribute)
                   and isinstance(stmt.value.func.value, ast.Name)
                   and stmt.value.func.value.id == "pytest"
                   and stmt.value.func.attr == "fail"
                   for stmt in guard.body):
            pytest.fail(f"{variable}: rejection must directly call pytest.fail")


def test_replay_db_sql_guards_are_direct_connection_statements():
    """Reject guards hidden in unreachable nested branches."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [node for node in ast.parse(source).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    connections = [node for node in ast.walk(fixture)
                   if isinstance(node, ast.AsyncWith)
                   and any(isinstance(item.context_expr, ast.Call)
                           and isinstance(item.context_expr.func, ast.Attribute)
                           and isinstance(item.context_expr.func.value, ast.Name)
                           and item.context_expr.func.value.id == "engine"
                           and item.context_expr.func.attr == "connect"
                           for item in node.items)]
    if len(connections) != 1:
        pytest.fail("Expected exactly one engine connection qualification block")
    statements = connections[0].body
    names = ("db_name", "server_version", "is_loopback", "present", "revision")
    for name in names:
        assignments = [i for i, stmt in enumerate(statements)
                       if isinstance(stmt, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == name
                               for target in stmt.targets)]
        if len(assignments) != 1:
            pytest.fail(f"{name}: qualification must be a direct connection statement")
        index = assignments[0]
        if index + 1 >= len(statements) or not isinstance(statements[index + 1], ast.If):
            pytest.fail(f"{name}: rejection must directly follow its SQL assignment")
        guard = statements[index + 1]
        if not any(isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                   and isinstance(stmt.value.func, ast.Attribute)
                   and isinstance(stmt.value.func.value, ast.Name)
                   and stmt.value.func.value.id == "pytest"
                   and stmt.value.func.attr == "fail" for stmt in guard.body):
            pytest.fail(f"{name}: rejection must directly call pytest.fail")


def test_replay_db_connection_qualification_is_reachable_before_session_yield():
    """Reject an unreachable connection block or a session yielded before qualification."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [node for node in ast.parse(source).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    tries = [node for node in fixture.body if isinstance(node, ast.Try)]
    if len(tries) != 1:
        pytest.fail("Expected one direct connection lifecycle try block")
    statements = tries[0].body
    if len(statements) != 2:
        pytest.fail("Connection qualification and session yield must be consecutive")
    connection, session_yield = statements
    if not (isinstance(connection, ast.AsyncWith)
            and len(connection.items) == 1
            and isinstance(connection.items[0].context_expr, ast.Call)
            and isinstance(connection.items[0].context_expr.func, ast.Attribute)
            and isinstance(connection.items[0].context_expr.func.value, ast.Name)
            and connection.items[0].context_expr.func.value.id == "engine"
            and connection.items[0].context_expr.func.attr == "connect"):
        pytest.fail("Connection qualification must be a direct, reachable try statement")
    if not (isinstance(session_yield, ast.Expr)
            and isinstance(session_yield.value, ast.Yield)
            and isinstance(session_yield.value.value, ast.Call)
            and isinstance(session_yield.value.value.func, ast.Name)
            and session_yield.value.value.func.id == "async_sessionmaker"):
        pytest.fail("Session must be yielded directly after the connection qualification")
    if sum(isinstance(node, (ast.Yield, ast.YieldFrom))
           for node in ast.walk(fixture)) != 1:
        pytest.fail("Expected exactly one session yield")


def test_replay_db_optimized_python_rejection_is_direct():
    """Reject an optimized-mode failure hidden inside an unreachable nested branch."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [node for node in ast.parse(source).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    fixture = fixtures[0]
    first = fixture.body[0] if fixture.body else None
    if not (isinstance(first, ast.If)
            and isinstance(first.test, ast.UnaryOp)
            and isinstance(first.test.op, ast.Not)
            and isinstance(first.test.operand, ast.Name)
            and first.test.operand.id == "__debug__"
            and len(first.body) == 1
            and not first.orelse):
        pytest.fail("Optimized-mode rejection must be a direct, unconditional guard")
    statement = first.body[0]
    if not (isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "pytest"
            and statement.value.func.attr == "fail"):
        pytest.fail("Optimized-mode guard must call pytest.fail directly")
