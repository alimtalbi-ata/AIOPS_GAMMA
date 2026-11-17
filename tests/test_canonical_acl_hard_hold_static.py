"""Static fail-closed guard for the unqualified canonical read integration.

Source-level check only; it cannot prove Gateway or upstream ACL correctness.
"""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "reused" / "upstream.py"


def test_canonical_read_function_has_only_allowlist_and_unconditional_denial():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "fetch_canonical"
    ]
    # A later definition would replace the guarded HOLD function at runtime.
    assert len(definitions) == 1
    fn = definitions[0]
    assert isinstance(fn, ast.AsyncFunctionDef)
    # No HTTP transport or config-dependent positive return may be added
    # until actor→tenant→resource authorization is independently qualified.
    assert len(fn.body) == 3  # docstring, allowlist check, unconditional denial
    assert isinstance(fn.body[0], ast.Expr)
    assert isinstance(fn.body[1], ast.If)
    assert isinstance(fn.body[2], ast.Raise)
    condition = fn.body[1]
    assert ast.unparse(condition.test) == "resource not in ALLOWED_RESOURCES"
    assert len(condition.body) == 1
    assert isinstance(condition.body[0], ast.Raise)
    assert "HTTPException(404" in ast.unparse(condition.body[0])
    assert "HTTPException(503" in ast.unparse(fn.body[2])
    assert "Canonical actor/tenant/resource ACL not qualified" in ast.unparse(fn.body[2])
    assert not any(isinstance(node, (ast.Await, ast.Return, ast.Yield, ast.YieldFrom))
                   for node in ast.walk(fn))

def test_canonical_hold_guard_rejects_positive_return(tmp_path, monkeypatch):
    """The static HOLD test must detect accidental fail-open edits."""
    import sys
    import pytest

    original = SOURCE.read_text(encoding="utf-8")
    changed = original.replace(
        '    raise HTTPException(503, "Canonical actor/tenant/resource ACL not qualified")',
        '    return {"tenant": str(tenant_id)}',
    )
    assert changed != original
    candidate = tmp_path / "upstream.py"
    candidate.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", candidate)
    with pytest.raises(AssertionError):
        test_canonical_read_function_has_only_allowlist_and_unconditional_denial()


def test_canonical_hold_guard_rejects_network_before_denial(tmp_path, monkeypatch):
    """A request issued before a 503 is not a safe HOLD."""
    import sys
    import pytest

    original = SOURCE.read_text(encoding="utf-8")
    changed = original.replace(
        '    raise HTTPException(503, "Canonical actor/tenant/resource ACL not qualified")',
        '    await httpx.AsyncClient().get("https://example.invalid")\n'
        '    raise HTTPException(503, "Canonical actor/tenant/resource ACL not qualified")',
    )
    assert changed != original
    candidate = tmp_path / "upstream.py"
    candidate.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", candidate)
    with pytest.raises(AssertionError):
        test_canonical_read_function_has_only_allowlist_and_unconditional_denial()


def test_canonical_hold_guard_rejects_later_function_override(tmp_path, monkeypatch):
    """Reject a second definition that replaces the fail-closed adapter."""
    import sys
    import pytest

    original = SOURCE.read_text(encoding="utf-8")
    changed = original + (
        "\n\nasync def fetch_canonical(resource, tenant_id):\n"
        "    return {'resource': resource, 'tenant': str(tenant_id)}\n"
    )
    candidate = tmp_path / "upstream.py"
    candidate.write_text(changed, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", candidate)
    with pytest.raises(AssertionError):
        test_canonical_read_function_has_only_allowlist_and_unconditional_denial()
