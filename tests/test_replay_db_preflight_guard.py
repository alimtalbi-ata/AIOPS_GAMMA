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


def test_replay_db_disposes_engine_directly_in_finally():
    """Require direct awaited engine disposal even if qualification or tests fail."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [node for node in ast.parse(source).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    tries = [node for node in fixtures[0].body if isinstance(node, ast.Try)]
    if len(tries) != 1:
        pytest.fail("Expected exactly one direct engine lifecycle try block")
    finalbody = tries[0].finalbody
    if len(finalbody) != 1:
        pytest.fail("Engine cleanup must be a direct finally statement")
    statement = finalbody[0]
    if not (isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Await)
            and isinstance(statement.value.value, ast.Call)
            and not statement.value.value.args
            and not statement.value.value.keywords
            and isinstance(statement.value.value.func, ast.Attribute)
            and isinstance(statement.value.value.func.value, ast.Name)
            and statement.value.value.func.value.id == "engine"
            and statement.value.value.func.attr == "dispose"):
        pytest.fail("Engine disposal must be directly awaited in finally")


def test_replay_db_write_acknowledgement_is_direct_before_engine_creation():
    """Require explicit write opt-in to fail directly before creating any engine."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    fixtures = [node for node in ast.parse(source).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    body = fixtures[0].body
    engines = [i for i, node in enumerate(body)
               if isinstance(node, ast.Assign)
               and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name)
               and node.value.func.id == "create_async_engine"]
    if len(engines) != 1 or engines[0] < 1:
        pytest.fail("Expected one direct engine creation after write acknowledgement")
    guard = body[engines[0] - 1]
    if not (isinstance(guard, ast.If)
            and not guard.orelse
            and len(guard.body) == 1
            and isinstance(guard.body[0], ast.Expr)
            and isinstance(guard.body[0].value, ast.Call)
            and isinstance(guard.body[0].value.func, ast.Attribute)
            and isinstance(guard.body[0].value.func.value, ast.Name)
            and guard.body[0].value.func.value.id == "pytest"
            and guard.body[0].value.func.attr == "fail"):
        pytest.fail("Write acknowledgement must reject directly before engine creation")
    expected = ast.parse(
        'os.environ.get("GAMMA_REPLAY_TEST_ALLOW_WRITE") != "I_UNDERSTAND_DISPOSABLE_DB"',
        mode="eval"
    ).body
    if ast.dump(guard.test) != ast.dump(expected):
        pytest.fail("Write acknowledgement must require the exact opt-in token")

def test_replay_db_loopback_sql_matches_reviewed_ipv4_ipv6_query():
    """Require the reviewed SQL expression, not just inet_server_addr() text."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    assignments = [
        node for node in ast.walk(fixtures[0])
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "is_loopback"
    ]
    if len(assignments) != 1:
        pytest.fail("Expected exactly one loopback SQL assignment")
    value = assignments[0].value
    if not (isinstance(value, ast.Await)
            and isinstance(value.value, ast.Call)
            and isinstance(value.value.func, ast.Attribute)
            and isinstance(value.value.func.value, ast.Name)
            and value.value.func.value.id == "connection"
            and value.value.func.attr == "scalar"
            and len(value.value.args) == 1):
        pytest.fail("Loopback qualification must await connection.scalar")
    query = value.value.args[0]
    if not (isinstance(query, ast.Call)
            and isinstance(query.func, ast.Name)
            and query.func.id == "text"
            and len(query.args) == 1
            and isinstance(query.args[0], ast.Constant)
            and isinstance(query.args[0].value, str)):
        pytest.fail("Loopback SQL must be a literal text() argument")
    expected = ("SELECT inet_server_addr() << inet '127.0.0.0/8' "
                "OR inet_server_addr() = inet '::1'")
    if query.args[0].value != expected:
        pytest.fail("Loopback SQL differs from reviewed IPv4/IPv6 expression")

def test_replay_db_disposable_url_validator_is_direct_before_engine():
    """Reject bypassing the disposable DB URL validator before engine creation."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    body = fixtures[0].body
    urls = [
        (index, node) for index, node in enumerate(body)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "url"
    ]
    if len(urls) != 1:
        pytest.fail("Expected exactly one direct URL assignment")
    index, assignment = urls[0]
    expected = ast.parse(
        'url = _require_disposable_database_url('
        'os.environ.get("GAMMA_REPLAY_TEST_DATABASE_URL", ""))'
    ).body[0].value
    if ast.dump(assignment.value) != ast.dump(expected):
        pytest.fail("URL must be validated directly using the disposable DB validator")
    if index == 0 or not isinstance(body[index - 1], ast.If):
        pytest.fail("URL validation must follow the optimized Python rejection")
    if index + 1 >= len(body) or not isinstance(body[index + 1], ast.If):
        pytest.fail("URL validation must precede explicit write acknowledgement")
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_async_engine"
        for statement in body[:index + 1] for node in ast.walk(statement)
    ):
        pytest.fail("Engine must not be created before URL validation")

def test_disposable_url_validator_rejects_unsafe_routing():
    """Require direct URL validation guards without pinning the entire function AST."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "_require_disposable_database_url"]
    if len(functions) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    body = functions[0].body
    required = (
        'not raw_url',
        'parsed.drivername != "postgresql+asyncpg"',
        'not parsed.database or not parsed.database.endswith("_replay_test")',
        'parsed.host not in ("localhost", "127.0.0.1", "::1")',
        'parsed.query',
    )
    for condition in required:
        expected = ast.dump(ast.parse(condition, mode="eval").body)
        guards = [node for node in body if isinstance(node, ast.If)
                  and ast.dump(node.test) == expected]
        if len(guards) != 1:
            pytest.fail(f"Missing direct URL guard: {condition}")
        direct = guards[0].body
        if (len(direct) != 1 or not isinstance(direct[0], ast.Expr)
                or not isinstance(direct[0].value, ast.Call)):
            pytest.fail(f"URL guard must reject directly: {condition}")
        call = direct[0].value
        method = "skip" if condition == "not raw_url" else "fail"
        if not (isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "pytest" and call.func.attr == method):
            pytest.fail(f"URL guard must call pytest.{method}: {condition}")
    tries = [node for node in body if isinstance(node, ast.Try)]
    if len(tries) != 1 or not any(
        isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "parsed"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "make_url" and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Name)
        and node.value.args[0].id == "raw_url"
        for node in tries[0].body
    ):
        pytest.fail("URL must be parsed directly in a guarded try block")
    if not any(isinstance(node, ast.Assign)
               and isinstance(node.value, ast.Attribute)
               and isinstance(node.value.value, ast.Name)
               and node.value.value.id == "parsed"
               and node.value.attr == "port" for node in tries[0].body):
        pytest.fail("URL port must be parsed eagerly")
    if (len(tries[0].handlers) != 1
            or not tries[0].handlers[0].body
            or not isinstance(tries[0].handlers[0].body[0], ast.Expr)):
        pytest.fail("Malformed URL exception must be handled")
    handler_call = tries[0].handlers[0].body[0].value
    if not (isinstance(handler_call, ast.Call)
            and isinstance(handler_call.func, ast.Attribute)
            and isinstance(handler_call.func.value, ast.Name)
            and handler_call.func.value.id == "pytest"
            and handler_call.func.attr == "fail"):
        pytest.fail("Malformed URL must fail")
    if (not isinstance(body[-1], ast.Return)
            or not isinstance(body[-1].value, ast.Name)
            or body[-1].value.id != "raw_url"):
        pytest.fail("Validator must return only the reviewed raw URL")


def test_disposable_url_validator_guards_precede_only_return():
    """Do not permit early returns that bypass disposable URL qualifications."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    validators = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_disposable_database_url"
    ]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    validator = validators[0]
    returns = [node for node in ast.walk(validator) if isinstance(node, ast.Return)]
    if len(returns) != 1 or returns[0] is not validator.body[-1]:
        pytest.fail("Disposable URL validator must have only one final return")
    if not (isinstance(returns[0].value, ast.Name)
            and returns[0].value.id == "raw_url"):
        pytest.fail("Disposable URL validator must return the validated raw URL")
    checks = [node for node in validator.body if isinstance(node, ast.If)]
    if len(checks) != 5 or not all(node.lineno < returns[0].lineno for node in checks):
        pytest.fail("All five direct URL guards must precede the final return")
    tries = [node for node in validator.body if isinstance(node, ast.Try)]
    if len(tries) != 1 or not (checks[0].lineno < tries[0].lineno < checks[1].lineno):
        pytest.fail("URL parsing must follow empty URL rejection and precede routing guards")


def test_disposable_url_validator_catches_expected_parse_errors():
    """Malformed URL parsing must fail closed for all expected error types."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(encoding="utf-8")
    validators = [node for node in ast.parse(source).body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "_require_disposable_database_url"]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    tries = [node for node in validators[0].body if isinstance(node, ast.Try)]
    if len(tries) != 1 or len(tries[0].handlers) != 1:
        pytest.fail("Expected exactly one guarded URL parsing block")
    handler = tries[0].handlers[0]
    if not isinstance(handler.type, ast.Tuple):
        pytest.fail("URL parsing must catch all reviewed exception types")
    actual = {node.id for node in handler.type.elts if isinstance(node, ast.Name)}
    if len(handler.type.elts) != 3 or actual != {"ArgumentError", "ValueError", "TypeError"}:
        pytest.fail("URL parsing must catch ArgumentError, ValueError and TypeError")


def test_disposable_url_validator_never_reassigns_parsed_url():
    """Validation must inspect the same URL that the fixture will use."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    validators = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_disposable_database_url"
    ]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    validator = validators[0]
    assignments = []
    for node in ast.walk(validator):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "parsed":
                    assignments.append(node)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            if isinstance(node.target, ast.Name) and node.target.id == "parsed":
                assignments.append(node)
    if len(assignments) != 1:
        pytest.fail("Parsed disposable URL must be assigned exactly once")
    assignment = assignments[0]
    if not (isinstance(assignment, ast.Assign)
            and len(assignment.targets) == 1
            and isinstance(assignment.value, ast.Call)
            and isinstance(assignment.value.func, ast.Name)
            and assignment.value.func.id == "make_url"
            and len(assignment.value.args) == 1
            and not assignment.value.keywords
            and isinstance(assignment.value.args[0], ast.Name)
            and assignment.value.args[0].id == "raw_url"):
        pytest.fail("Parsed URL must come exclusively from make_url(raw_url)")


def test_disposable_url_validator_rejects_destructured_parsed_rebinding():
    """Tuple unpacking must not replace the parsed user-supplied URL."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    validators = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_disposable_database_url"
    ]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    stores = [
        node for node in ast.walk(validators[0])
        if isinstance(node, ast.Name)
        and node.id == "parsed"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(stores) != 1:
        pytest.fail("Parsed URL must have exactly one binding, including unpacking")


def test_disposable_url_validator_never_rebinds_raw_url():
    """The returned URL must remain the exact input that passed the guards."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    validators = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_disposable_database_url"
    ]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    writes = [
        node for node in ast.walk(validators[0])
        if isinstance(node, ast.Name)
        and node.id == "raw_url"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if writes:
        pytest.fail("Disposable URL input must never be rebound or deleted")


def test_replay_db_engine_uses_only_validated_url():
    """The engine must receive the exact URL returned by the disposable preflight."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    body = fixtures[0].body
    url_bindings = [
        node for node in ast.walk(fixtures[0])
        if isinstance(node, ast.Name)
        and node.id == "url"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(url_bindings) != 1:
        pytest.fail("Validated URL must have exactly one binding")
    assignments = [
        node for node in body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "url"
    ]
    if len(assignments) != 1:
        pytest.fail("Validated URL must be assigned directly in the fixture")
    assignment = assignments[0]
    if not (isinstance(assignment.value, ast.Call)
            and isinstance(assignment.value.func, ast.Name)
            and assignment.value.func.id == "_require_disposable_database_url"
            and len(assignment.value.args) == 1
            and not assignment.value.keywords):
        pytest.fail("URL must originate from the disposable preflight")
    engines = [
        node for node in body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "create_async_engine"
    ]
    if len(engines) != 1:
        pytest.fail("Expected exactly one direct engine creation")
    call = engines[0].value
    if not (len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "url"
            and assignment.lineno < engines[0].lineno):
        pytest.fail("Engine must consume the previously validated URL directly")


def test_replay_db_engine_binding_cannot_be_replaced():
    """A validated engine must not be replaced before database qualifications."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    writes = [
        node for node in ast.walk(fixtures[0])
        if isinstance(node, ast.Name)
        and node.id == "engine"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if len(writes) != 1:
        pytest.fail("Replay engine must have exactly one binding")


def test_replay_db_sessionmaker_uses_qualified_engine():
    """The yielded session factory must use the same engine that was qualified."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    yields = [node for node in ast.walk(fixtures[0]) if isinstance(node, ast.Yield)]
    if len(yields) != 1 or not isinstance(yields[0].value, ast.Call):
        pytest.fail("Expected one direct session factory yield")
    call = yields[0].value
    if not (isinstance(call.func, ast.Name)
            and call.func.id == "async_sessionmaker"
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "engine"
            and len(call.keywords) == 1
            and call.keywords[0].arg == "expire_on_commit"
            and isinstance(call.keywords[0].value, ast.Constant)
            and call.keywords[0].value.value is False):
        pytest.fail("Session factory must use only the qualified engine")


def test_replay_db_fixture_cannot_shadow_qualified_session_factory_via_arguments():
    """Fixture arguments must not replace the reviewed session factory binding."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    fixtures = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "replay_db"
    ]
    if len(fixtures) != 1:
        pytest.fail("Expected exactly one replay_db fixture")
    arguments = fixtures[0].args
    if (arguments.posonlyargs or arguments.args or arguments.kwonlyargs
            or arguments.vararg is not None or arguments.kwarg is not None
            or arguments.defaults or any(v is not None for v in arguments.kw_defaults)):
        pytest.fail("Replay fixture must not accept arguments that shadow security bindings")


def test_disposable_url_validator_does_not_shadow_url_parser():
    """The URL parser must not be locally replaced before validating the DSN."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    validators = [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_disposable_database_url"
    ]
    if len(validators) != 1:
        pytest.fail("Expected exactly one disposable URL validator")
    writes = [
        node for node in ast.walk(validators[0])
        if isinstance(node, ast.Name)
        and node.id == "make_url"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ]
    if writes:
        pytest.fail("Disposable URL parser must not be locally shadowed")


def test_replay_db_security_dependencies_not_shadowed_at_module_scope():
    """Module-level rebinding must not replace reviewed DB safety dependencies."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    protected = {"make_url", "create_async_engine", "async_sessionmaker", "pytest"}
    tree = ast.parse(source)
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if statement.name in protected:
                pytest.fail(f"Module-level dependency shadowed: {statement.name}")
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            for node in ast.walk(statement):
                if (isinstance(node, ast.Name) and node.id in protected
                        and isinstance(node.ctx, (ast.Store, ast.Del))):
                    pytest.fail(f"Module-level dependency shadowed: {node.id}")


def test_replay_db_security_dependencies_not_rebound_by_module_loops():
    """Top-level loop targets cannot replace reviewed database dependencies."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    protected = {"make_url", "create_async_engine", "async_sessionmaker", "pytest"}
    for statement in ast.parse(source).body:
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            for node in ast.walk(statement.target):
                if (isinstance(node, ast.Name) and node.id in protected
                        and isinstance(node.ctx, (ast.Store, ast.Del))):
                    pytest.fail(f"Module-level loop shadows security dependency: {node.id}")


def test_replay_db_security_dependencies_not_shadowed_in_nested_module_control_flow():
    """Module-scope branches and loops cannot rebind DB safety dependencies."""
    source = (Path(__file__).parent / "test_gateway_replay_postgres.py").read_text(
        encoding="utf-8"
    )
    protected = {"make_url", "create_async_engine", "async_sessionmaker", "pytest"}

    class ModuleBindingVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            return

        def visit_AsyncFunctionDef(self, node):
            return

        def visit_ClassDef(self, node):
            return

        def visit_Lambda(self, node):
            return

        def visit_Name(self, node):
            if node.id in protected and isinstance(node.ctx, (ast.Store, ast.Del)):
                pytest.fail(f"Module control flow shadows security dependency: {node.id}")

    visitor = ModuleBindingVisitor()
    for statement in ast.parse(source).body:
        visitor.visit(statement)
