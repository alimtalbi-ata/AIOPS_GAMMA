"""Dependency-light, executable contract for incident ID canonicalization.

Extract only the validator AST from app/main.py: no database, gateway or service
imports are needed. This is NOT an HTTP or PostgreSQL integration test.
"""
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException


MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _validator():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "validate_incident_resource_id"
    )
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    namespace = {"HTTPException": HTTPException}
    exec(compile(module, str(MAIN), "exec"), namespace)
    return namespace["validate_incident_resource_id"]


@pytest.mark.parametrize("value", [
    "inc-1", "caf\u00e9", "x" * 255, "A_B.9", "\u6771\u4eac", "a:b",
])
def test_valid_canonical_incident_ids(value):
    assert _validator()(value) == value


@pytest.mark.parametrize("value", [
    "", "x" * 256, " inc", "inc ", "inc/name", "inc\\\\name",
    "inc?name", "inc#name", "*", "cafe\u0301", "inc\u0085name",
    "inc\u200bname", "inc\u202ename", "inc\x00name",
    "inc\x7fname", "inc\ud800name",
])
def test_invalid_incident_ids_fail_closed(value):
    with pytest.raises(HTTPException) as error:
        _validator()(value)
    assert error.value.status_code == 422
