"""Static guard for fail-closed replay helper semantics.

This AST/source contract does not prove PostgreSQL behavior or concurrency safety.
"""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "gateway_replay.py"


def _module():
    return ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _function(tree, name):
    return next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


def _call_names(node):
    return {
        child.func.attr if isinstance(child.func, ast.Attribute)
        else child.func.id if isinstance(child.func, ast.Name)
        else None
        for child in ast.walk(node) if isinstance(child, ast.Call)
    }


def test_reservation_uses_sha256_digest_and_atomic_conflict_handling():
    tree = _module()
    function = _function(tree, "reserve_assertion_once")
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), function)
    assert "hashlib.sha256" in source
    assert 'issuer + "\\x00" + assertion_id' in source
    assert "ON CONFLICT (assertion_digest) DO NOTHING" in source
    assert "RETURNING assertion_digest" in source
    assert "assertion_id" not in source.split("text(", 1)[1].split(")", 1)[0]


def test_reservation_validates_inputs_before_database_execute():
    tree = _module()
    function = _function(tree, "reserve_assertion_once")
    calls = [
        child.func.attr for child in ast.walk(function)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
    ]
    assert calls.index("execute") > calls.index("sha256")
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), function)
    assert "isinstance(issuer, str)" in source
    assert "assertion_id.isascii()" in source
    assert "type(expires_at) is not int" in source


def test_consume_commits_before_success_and_rolls_back_failure_paths():
    tree = _module()
    function = _function(tree, "consume_assertion_before_access")
    calls = [child.func.attr for child in ast.walk(function)
             if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)]
    assert "commit" in calls
    assert "rollback" in calls
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), function)
    assert source.index("await session.commit()") < source.index("return True")
    assert "if not reserved:" in source
    assert "await session.rollback()" in source
