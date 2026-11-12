"""Static contract for selected tenant-scoped resource routes.

This is source-level regression coverage only. It does not prove database ACLs,
Gateway membership, or cross-tenant behavior against a running PostgreSQL API.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"


def _routes():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "app"
            and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
            for decorator in node.decorator_list
        )
    }


def _source(node):
    return ast.get_source_segment(MAIN.read_text(encoding="utf-8"), node)


def test_resource_create_routes_take_tenant_only_from_verified_principal():
    routes = _routes()
    for name in ("add_binding", "add_evidence"):
        source = _source(routes[name])
        assert "principal: Principal = Depends(internal_principal)" in source
        assert "tenant_id=principal.tenant_id" in source
    assert "req.tenant_id" not in _source(routes["add_binding"])
    assert "req.tenant_id" not in _source(routes["add_evidence"])


def test_resource_list_routes_filter_by_principal_tenant_and_resource_id():
    routes = _routes()
    bindings = _source(routes["list_bindings"])
    evidence = _source(routes["list_evidence"])
    assert "principal: Principal = Depends(internal_principal)" in bindings
    assert "ServiceBinding.tenant_id == principal.tenant_id" in bindings
    assert "principal: Principal = Depends(internal_principal)" in evidence
    assert "Evidence.tenant_id == principal.tenant_id" in evidence
    assert "Evidence.incident_id == incident_id" in evidence


def test_tenant_supplied_preview_payloads_are_checked_against_principal():
    routes = _routes()
    itil = _source(routes["itil_workflow_preview"])
    evidence = _source(routes["evidence_preview"])
    assert "req.incident.tenant_id != principal.tenant_id" in itil
    assert "raise HTTPException(403" in itil
    assert "item.tenant_id != str(principal.tenant_id)" in evidence
    assert "raise HTTPException(403" in evidence


def test_correlation_and_investigation_use_authenticated_tenant_context():
    routes = _routes()
    correlation = _source(routes["correlation_evidence_preview"])
    investigation = _source(routes["investigation_preview"])
    assert "principal: Principal = Depends(internal_principal)" in correlation
    assert "str(principal.tenant_id)" in correlation
    assert "principal: Principal = Depends(internal_principal)" in investigation
    assert "evaluate_investigation(req, principal.tenant_id)" in investigation
