"""Conservative scope-claim rejection adapted from aiops/app/shared/tenant_scope.py.

Used only on untrusted upstream diagnostic metadata, not on authenticated
internal tenant identity. This does not implement tenant authorization.
"""
import re
import unicodedata

NAMES = frozenset((
    "tenant", "tenantid", "tenantname", "tenantkey", "tenantids",
    "org", "orgid", "orgname", "organization", "organizationid",
    "workspace", "workspaceid", "workspacename",
    "account", "accountid", "accountname",
    "customer", "customerid", "customername",
    "tenantaclqualified", "aclqualified", "orgref", "organizationref",
    "workspaceref", "accountref", "customerref",
))


def reject_unqualified_tenant_scope(value: object) -> None:
    pending = [value]
    visited = 0
    while pending:
        item = pending.pop()
        visited += 1
        if visited > 4096:
            raise ValueError("tenant-scope scan bound exceeded")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("invalid tenant-scope key")
                normalized = re.sub(
                    r"[^a-z0-9]", "", unicodedata.normalize("NFKC", key).casefold()
                )
                if (normalized in NAMES
                    or normalized.startswith(("tenant", "organization", "workspace"))
                    or normalized.endswith((
                        "tenant", "tenantid", "orgid", "organizationid",
                        "workspaceid", "accountid", "customerid",
                    ))):
                    raise ValueError("unqualified tenant scope claim")
                pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)
