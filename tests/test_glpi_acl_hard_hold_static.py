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


def test_glpi_http_route_cannot_bypass_public_acl_hold():
    """The FastAPI snapshot route must call the guarded public entrypoint only."""
    route_source = SOURCE.parents[1] / "main.py"
    tree = ast.parse(route_source.read_text(encoding="utf-8"))
    # The route's public function name must resolve to the guarded adapter,
    # not a similarly named helper or a reassigned module-level symbol.
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == "app.reused.glpi_read"]
    assert len(imports) == 1
    assert [(alias.name, alias.asname) for alias in imports[0].names] == [
        ("read_glpi_incident", None)
    ]
    assert not any(
        isinstance(node, (ast.Assign, ast.AnnAssign, ast.FunctionDef,
                          ast.AsyncFunctionDef, ast.ClassDef))
        and (
            (isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name)
                     and target.id == "read_glpi_incident"
                     for target in node.targets))
            or (isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "read_glpi_incident")
            or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == "read_glpi_incident")
        )
        for node in tree.body
    )
    routes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "glpi_incident_snapshot"]
    assert len(routes) == 1
    route = routes[0]
    # No side-effect, alternate return, or transport call can be inserted before
    # the public fail-closed entrypoint.
    assert len(route.body) == 2
    assert isinstance(route.body[0], ast.Assign)
    header_assignment = route.body[0]
    assert len(header_assignment.targets) == 1
    target = header_assignment.targets[0]
    assert isinstance(target, ast.Subscript)
    assert isinstance(target.value, ast.Attribute)
    assert isinstance(target.value.value, ast.Name)
    assert target.value.value.id == "response"
    assert target.value.attr == "headers"
    assert isinstance(target.slice, ast.Constant)
    assert target.slice.value == "Cache-Control"
    assert isinstance(header_assignment.value, ast.Constant)
    assert header_assignment.value.value == "no-store"
    assert isinstance(route.body[1], ast.Return)
    returned = route.body[1].value
    assert isinstance(returned, ast.Await)
    assert isinstance(returned.value, ast.Call)
    assert isinstance(returned.value.func, ast.Name)
    assert returned.value.func.id == "read_glpi_incident"
    assert [ast.unparse(arg) for arg in returned.value.args] == [
        "principal.tenant_id", "ticket_id"
    ]
    assert not returned.value.keywords


def test_glpi_route_guard_rejects_transport_bypass(tmp_path, monkeypatch):
    import sys

    original = (SOURCE.parents[1] / "main.py").read_text(encoding="utf-8")
    target = "return await read_glpi_incident(principal.tenant_id, ticket_id)"
    assert target in original
    changed = original.replace(
        target,
        "return await _read_glpi_incident_unqualified(principal.tenant_id, ticket_id)",
        1,
    )
    # The route guard reads the application source; monkeypatch its source root
    # to an isolated copy so this mutation test never touches production code.
    source_dir = tmp_path / "app" / "reused"
    source_dir.mkdir(parents=True)
    fake_source = source_dir / "glpi_read.py"
    fake_source.write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(changed, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", fake_source)
    with pytest.raises(AssertionError):
        test_glpi_http_route_cannot_bypass_public_acl_hold()


def test_glpi_route_guard_rejects_import_alias_bypass(tmp_path, monkeypatch):
    """A same-name import from an unqualified adapter must fail the route guard."""
    import sys

    original = (SOURCE.parents[1] / "main.py").read_text(encoding="utf-8")
    target = "from app.reused.glpi_read import read_glpi_incident"
    assert target in original
    changed = original.replace(
        target,
        "from app.reused.glpi_read import "
        "_read_glpi_incident_unqualified as read_glpi_incident",
        1,
    )
    source_dir = tmp_path / "app" / "reused"
    source_dir.mkdir(parents=True)
    fake_source = source_dir / "glpi_read.py"
    fake_source.write_text("", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(changed, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", fake_source)
    with pytest.raises(AssertionError):
        test_glpi_http_route_cannot_bypass_public_acl_hold()
