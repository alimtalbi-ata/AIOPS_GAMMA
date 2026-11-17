"""Source-level GLPI public-entrypoint HOLD guard; not a runtime ACL qualification.

The private _read_glpi_incident_unqualified helper is intentionally excluded:
it is an offline transport test seam, never an authorized API entrypoint.
"""
import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "app" / "reused" / "glpi_read.py"


def assert_public_glpi_hold(source: str) -> None:
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "read_glpi_incident"
    )
    # Exactly: docstring, invalid ticket check, unconditional ACL denial.
    assert len(function.body) == 3
    assert isinstance(function.body[0], ast.Expr)
    assert isinstance(function.body[1], ast.If)
    assert isinstance(function.body[2], ast.Raise)
    ticket_check = function.body[1]
    assert len(ticket_check.body) == 1
    assert not ticket_check.orelse
    assert ast.unparse(ticket_check.test) == "type(ticket_id) is not int or ticket_id <= 0"
    assert isinstance(ticket_check.body[0], ast.Raise)
    assert "HTTPException(422" in ast.unparse(ticket_check.body[0])
    assert "Invalid GLPI ticket id" in ast.unparse(ticket_check.body[0])
    assert "HTTPException(503" in ast.unparse(function.body[2])
    assert "GLPI actor/tenant/resource ACL not qualified" in ast.unparse(function.body[2])
    assert "no-store" in ast.unparse(ticket_check.body[0])
    assert "no-store" in ast.unparse(function.body[2])
    # Neither feature flags nor transport helpers can make the public function
    # return a snapshot, call the network or perform an await before denial.
    assert not any(
        isinstance(node, (ast.Await, ast.Return, ast.Yield, ast.YieldFrom))
        for node in ast.walk(function)
    )


def test_public_glpi_entrypoint_unconditionally_denies_unqualified_reads():
    assert_public_glpi_hold(SOURCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("replacement", [
    '    return {"ticket_id": ticket_id}',
    '    await _read_glpi_incident_unqualified(tenant_id, ticket_id)\n'
    '    raise HTTPException(503, "GLPI actor/tenant/resource ACL not qualified", '
    'headers={"Cache-Control": "no-store"})',
])
def test_glpi_hold_guard_detects_fail_open_mutation(replacement):
    original = SOURCE.read_text(encoding="utf-8")
    target = '    raise HTTPException(503, "GLPI actor/tenant/resource ACL not qualified",\n' \
             '                        headers={"Cache-Control": "no-store"})'
    assert target in original
    mutated = original.replace(target, replacement, 1)
    assert mutated != original
    with pytest.raises(AssertionError):
        assert_public_glpi_hold(mutated)


def test_glpi_hold_guard_detects_invalid_ticket_condition_bypass():
    original = SOURCE.read_text(encoding="utf-8")
    target = "if type(ticket_id) is not int or ticket_id <= 0:"
    assert target in original
    changed = original.replace(target, "if ticket_id == 7:", 1)
    with pytest.raises(AssertionError):
        assert_public_glpi_hold(changed)
