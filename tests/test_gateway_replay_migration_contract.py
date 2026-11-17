"""Static contract checks for the staged PostgreSQL replay migration.

These checks inspect migration source without connecting to or mutating a DB.
They do not replace Alembic upgrade/downgrade or PostgreSQL concurrency tests.
"""
import ast
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0002_gateway_replay.py"


def _migration_tree():
    return ast.parse(MIGRATION.read_text(encoding="utf-8"), filename=str(MIGRATION))


def _calls(tree, function_name):
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == function_name
    ]


def test_replay_migration_revision_chain_is_explicit():
    tree = _migration_tree()
    assignments = {
        target.id: value.value
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
        and isinstance(value := node.value, ast.Constant)
    }
    assert assignments["revision"] == "0002_gateway_replay"
    assert assignments["down_revision"] == "0001_initial"


def test_replay_table_uses_digest_primary_key_and_aware_expiry():
    tree = _migration_tree()
    calls = _calls(tree, "create_table")
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call.args[0], ast.Constant)
    assert call.args[0].value == "gateway_assertion_replay"
    columns = {
        arg.args[0].value: arg
        for arg in call.args[1:]
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and isinstance(arg.func.value, ast.Name)
        and arg.func.value.id == "sa"
        and arg.func.attr == "Column"
        and arg.args and isinstance(arg.args[0], ast.Constant)
    }
    assert set(columns) == {"assertion_digest", "expires_at"}
    digest = ast.unparse(columns["assertion_digest"])
    expiry = ast.unparse(columns["expires_at"])
    assert "String(length=64)" in digest
    assert "primary_key=True" in digest
    assert "DateTime(timezone=True)" in expiry
    assert "nullable=False" in expiry


def test_replay_expiry_index_is_non_unique_and_targets_expiry():
    tree = _migration_tree()
    calls = _calls(tree, "create_index")
    assert len(calls) == 1
    assert ast.unparse(calls[0]) == (
        "op.create_index('ix_gateway_assertion_replay_expires_at', "
        "'gateway_assertion_replay', ['expires_at'], unique=False)"
    )


def test_downgrade_drops_index_before_replay_table():
    tree = _migration_tree()
    downgrade = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    )
    calls = [
        node for node in ast.walk(downgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    ]
    names = [node.func.attr for node in calls]
    assert names == ["drop_index", "drop_table"]
