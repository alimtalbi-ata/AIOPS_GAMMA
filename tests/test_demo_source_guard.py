"""Static review of public demo helper code; no imports or network."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'app' / 'demo.py'
ALLOWED_IMPORTS = {'datetime', 'app.reused.correlation', 'app.reused.correlation_evidence', 'app.reused.evidence'}
ALLOWED_HELPERS = {'synthetic_correlation_demo', 'synthetic_investigation_demo'}


def check_source(source):
    tree = ast.parse(source)
    assert {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))} == ALLOWED_HELPERS
    assert not any(isinstance(n, ast.AsyncFunctionDef) for n in ast.walk(tree))
    for n in ast.walk(tree):
        assert not isinstance(n, (ast.Import, ast.Global, ast.Nonlocal, ast.Await, ast.Yield, ast.YieldFrom))
        if isinstance(n, ast.ImportFrom):
            assert n.module in ALLOWED_IMPORTS, n.module
        if isinstance(n, ast.Call):
            assert isinstance(n.func, (ast.Name, ast.Attribute))
            if isinstance(n.func, ast.Name):
                assert n.func.id in {'datetime', 'CorrelationSignal', 'correlate', 'CorrelationPreview', 'CorrelationEvidencePreview', 'EvidenceInput', 'preview', 'range'}
            else:
                assert isinstance(n.func.value, ast.Name) and n.func.attr == 'replace' and n.func.value.id == 'observed'
    assert source.count('"authoritative": False') == 2
    assert '"evidence_source_verified": False' in source


def test_authentic_demo_static():
    check_source(SOURCE.read_text())


def test_network_mutation_rejected():
    import pytest
    with pytest.raises(AssertionError):
        check_source(SOURCE.read_text().replace('    signals = [', '    import requests\n    requests.get("https://example.invalid")\n    signals = [', 1))


def test_authoritative_mutation_rejected():
    import pytest
    with pytest.raises(AssertionError):
        check_source(SOURCE.read_text().replace('"authoritative": False', '"authoritative": True', 1))
