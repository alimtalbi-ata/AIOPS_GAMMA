"""Static safety contracts for integrated replay enforcement and rollout gates.

Source checks do not prove live PostgreSQL concurrency or deployed Gateway ACLs.
Production qualification remains separate from enforcement in the integrated code.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _imports_replay(tree):
    return any(
        isinstance(node, ast.ImportFrom) and node.module == "app.gateway_replay"
        or isinstance(node, ast.Import)
        and any(alias.name == "app.gateway_replay" for alias in node.names)
        for node in ast.walk(tree)
    )


def _assert_authentication_consumes_replay(source):
    """Pin the reviewed async gate, including ordering and fail-closed paths."""
    security = ast.parse(source)
    assert _imports_replay(security)
    function = next(node for node in security.body
                    if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "internal_principal")
    expected = ast.parse('''
async def gate():
    principal = verify_gateway_assertion(
        x_gateway_principal, method=request.method, path=request.url.path
    )
    try:
        async with get_session_factory()() as replay_session:
            consumed = await consume_assertion_before_access(
                replay_session, issuer=settings.gateway_assertion_issuer,
                assertion_id=principal.assertion_id, expires_at=principal.expires_at,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Gateway replay protection unavailable"
        ) from exc
    if not consumed:
        raise HTTPException(status_code=401, detail="Gateway assertion already used")
    return principal
''').body[0].body
    assert len(function.body) >= len(expected)
    actual = function.body[-len(expected):]
    assert [ast.dump(node) for node in actual] == [ast.dump(node) for node in expected]
    assert not any(isinstance(node, ast.Return)
                   for statement in function.body[:-len(expected)]
                   for node in ast.walk(statement)), "Early authentication bypass"


def test_authentication_consumes_replay_before_access():
    _assert_authentication_consumes_replay(_source("app/security.py"))


def test_authentication_replay_gate_mutations_are_rejected():
    import pytest

    source = _source("app/security.py")
    for original, replacement in (
        ("consumed = await consume_assertion_before_access(", "consumed = consume_assertion_before_access("),
        ("if not consumed:", "if False:"),
        ("status_code=503, detail=\"Gateway replay protection unavailable\"", "status_code=401, detail=\"Gateway replay protection unavailable\""),
        ("    principal = verify_gateway_assertion(", "    return None\n    principal = verify_gateway_assertion("),
    ):
        assert original in source
        with pytest.raises(AssertionError):
            _assert_authentication_consumes_replay(source.replace(original, replacement, 1))


def test_api_entrypoint_does_not_wire_replay_helper():
    main = ast.parse(_source("app/main.py"))
    assert not _imports_replay(main)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
        and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
        in {"consume_assertion_before_access", "reserve_assertion_once"}
        for node in ast.walk(main)
    )


def test_disposable_postgres_job_keeps_explicit_safety_gates():
    workflow = _source(".github/workflows/ci.yml")
    # This is a narrow fail-safe source guard, not a general YAML validator.
    assert "gateway-replay-postgres:" in workflow
    job = workflow.split("  gateway-replay-postgres:", 1)[1].split("\n  tenant-evidence-postgres:", 1)[0]
    assert "postgres:16 -c listen_addresses=127.0.0.1" in job
    assert "-e POSTGRES_DB=gamma_replay_test" in job
    assert "--network host" in job
    assert "docker rm -f gamma-replay-ci" in job
    assert "127.0.0.1:5432/gamma_replay_test" in job
    assert "GAMMA_REPLAY_TEST_ALLOW_WRITE: I_UNDERSTAND_DISPOSABLE_DB" in job
    assert "run: alembic upgrade 0002_gateway_replay" in job
    assert "run: python -m pytest -q tests/test_gateway_replay_postgres.py" in job
    assert job.index("run: alembic upgrade 0002_gateway_replay") < job.index(
        "run: python -m pytest -q tests/test_gateway_replay_postgres.py"
    )


def test_postgres_integration_fixture_refuses_non_disposable_urls():
    test_source = _source("tests/test_gateway_replay_postgres.py")
    assert 'parsed.drivername != "postgresql+asyncpg"' in test_source
    assert 'parsed.database.endswith("_replay_test")' in test_source
    assert '"127.0.0.1"' in test_source
    assert 'SELECT current_database()' in test_source
    assert 'revision != "0002_gateway_replay"' in test_source



def test_disposable_postgres_ci_roundtrip_precedes_concurrency_tests():
    """Guard migration rollback/reapply coverage without claiming it ran."""
    workflow = _source(".github/workflows/ci.yml")
    job = workflow.split("  gateway-replay-postgres:", 1)[1].split("\n  tenant-evidence-postgres:", 1)[0]
    required = (
        "run: alembic upgrade 0002_gateway_replay",
        "alembic downgrade 0001_initial",
        "alembic upgrade 0002_gateway_replay",
        'SELECT current_database()',
        'SELECT version_num FROM alembic_version',
        "SELECT to_regclass('gateway_assertion_replay')",
        "run: python -m pytest -q tests/test_gateway_replay_postgres.py",
    )
    positions = []
    for marker in required:
        positions.append(job.index(marker, positions[-1] + 1 if positions else 0))
    assert positions == sorted(positions)
    assert '== "gamma_replay_test"' in job
    assert '== "0002_gateway_replay"' in job


def test_replay_migration_downgrade_is_scoped_to_replay_objects():
    """Prevent accidental broad schema drops in the replay-only migration."""
    migration = ast.parse(_source("migrations/versions/0002_gateway_replay.py"))
    downgrade = next(
        node for node in migration.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "downgrade"
    )
    calls = [
        node for node in ast.walk(downgrade)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    drop_calls = [
        node for node in calls if node.func.attr.startswith("drop_")
    ]
    assert len(drop_calls) == 2
    assert {node.func.attr for node in drop_calls} == {"drop_index", "drop_table"}
    for node in drop_calls:
        assert isinstance(node.args[0], ast.Constant)
        assert node.args[0].value in {
            "ix_gateway_assertion_replay_expires_at", "gateway_assertion_replay"
        }
