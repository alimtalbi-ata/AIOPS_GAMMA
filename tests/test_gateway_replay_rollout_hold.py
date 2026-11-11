"""Static safety contract for the pending gateway replay rollout.

These guards deliberately do not enable replay enforcement or prove live ACLs.
They assert that the integration remains OFF until real PostgreSQL and Gateway
actor-to-tenant-to-resource qualification has been recorded.
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


def test_authentication_still_does_not_consume_replay_reservations():
    # Check executable imports/calls, not a comment or a documentation string.
    security = ast.parse(_source("app/security.py"))
    assert not _imports_replay(security)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
        and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
        in {"consume_assertion_before_access", "reserve_assertion_once"}
        for node in ast.walk(security)
    )


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
    job = workflow.split("  gateway-replay-postgres:", 1)[1]
    assert "image: postgres:16" in job
    assert "POSTGRES_DB: gamma_replay_test" in job
    assert "127.0.0.1:5432/gamma_replay_test" in job
    assert "GAMMA_REPLAY_TEST_ALLOW_WRITE: I_UNDERSTAND_DISPOSABLE_DB" in job
    assert "run: alembic upgrade head" in job
    assert "run: python -m pytest -q tests/test_gateway_replay_postgres.py" in job
    assert job.index("run: alembic upgrade head") < job.index(
        "run: python -m pytest -q tests/test_gateway_replay_postgres.py"
    )


def test_postgres_integration_fixture_refuses_non_disposable_urls():
    test_source = _source("tests/test_gateway_replay_postgres.py")
    assert 'parsed.drivername != "postgresql+asyncpg"' in test_source
    assert 'parsed.database.endswith("_replay_test")' in test_source
    assert '"127.0.0.1"' in test_source
    assert 'SELECT current_database()' in test_source
    assert 'revision == "0002_gateway_replay"' in test_source
