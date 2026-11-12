"""Static fail-closed guard for the unqualified canonical read integration.

Source-level check only; it cannot prove Gateway or upstream ACL correctness.
"""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "reused" / "upstream.py"


def test_canonical_read_function_has_only_allowlist_and_unconditional_denial():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "fetch_canonical")
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
