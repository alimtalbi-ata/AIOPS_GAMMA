"""Fail-closed checks for untrusted diagnostic tenant-scope metadata."""
import pytest
from app.reused.tenant_scope import reject_unqualified_tenant_scope


@pytest.mark.parametrize("key", [
    "tenant", "Tenant-ID", "TENANT_ID", "workspace.name",
    "organizationRef", "account_id", "customer-id", "Ｔｅｎａｎｔ",
])
def test_nested_untrusted_scope_claim_rejected(key):
    with pytest.raises(ValueError, match="unqualified tenant scope"):
        reject_unqualified_tenant_scope({"diagnostics": [{"metadata": {key: "forged"}}]})


def test_non_string_key_rejected():
    with pytest.raises(ValueError, match="invalid tenant-scope key"):
        reject_unqualified_tenant_scope({42: "untrusted"})


def test_scan_bound_fails_closed():
    with pytest.raises(ValueError, match="scan bound exceeded"):
        reject_unqualified_tenant_scope([{} for _ in range(4097)])


def test_benign_nested_metadata_allowed():
    reject_unqualified_tenant_scope({"event": [{"source": "synthetic", "severity": "P3"}]})
