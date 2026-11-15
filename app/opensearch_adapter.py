from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit
from uuid import UUID

from app.schemas import LogSearchRequest
from app.settings import settings


def make_log_query(tenant_id: str, req: LogSearchRequest) -> dict:
    # Defense in depth: never construct an unscoped or malformed tenant query.
    try:
        parsed_tenant = UUID(tenant_id)
        if parsed_tenant.int == 0:
            raise ValueError("Nil tenant UUID is not a tenant identity")
        canonical_tenant = str(parsed_tenant)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Valid tenant UUID required for OpenSearch query") from exc
    if tenant_id != canonical_tenant:
        raise ValueError("Canonical tenant UUID required for OpenSearch query")
    # Defense in depth for direct callers: revalidate potentially mutated model data.
    req = LogSearchRequest.model_validate(req.model_dump())
    # Direct adapter callers must not bypass the HTTP endpoint's query-window policy.
    if settings.max_query_hours <= 0:
        raise ValueError("OpenSearch query window policy must be positive")
    if req.window.end - req.window.start > timedelta(hours=settings.max_query_hours):
        raise ValueError("OpenSearch query window exceeds policy")
    filters = [
        {"term": {"tenant.id": tenant_id}},
        {"term": {"resource.attributes.service.name": req.service_name}},
        {"range": {"@timestamp": {
            "gte": req.window.start.isoformat(), "lte": req.window.end.isoformat()
        }}},
    ]
    if req.severity:
        filters.append({"terms": {"severityText": req.severity}})
    return {
        "size": req.limit,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"bool": {"filter": filters}},
        "track_total_hits": False,
    }


def validate_opensearch_transport() -> None:
    """Fail closed on unsafe remote transport and credential-bearing URLs."""
    try:
        url = urlsplit(settings.opensearch_url)
        host = url.hostname
        port = url.port
    except ValueError as exc:
        raise ValueError("Invalid OpenSearch endpoint") from exc
    if (
        url.scheme not in ("http", "https")
        or not host
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in ("", "/")
        or port == 0
    ):
        raise ValueError("Invalid OpenSearch endpoint")
    # Prevent misconfiguration from turning a tenant-scoped read into an
    # all-index or multi-index search. Wildcards are suffix-only on a fixed prefix.
    index = settings.opensearch_logs_index
    if not isinstance(index, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,127}[*]?", index):
        raise ValueError("OpenSearch logs index must be a bounded explicit prefix")
    if index in ("_all", "*") or index.startswith((".", "_")):
        raise ValueError("OpenSearch logs index must be a bounded explicit prefix")
    if settings.opensearch_url != settings.opensearch_url.strip():
        raise ValueError("Invalid OpenSearch endpoint")
    if bool(settings.opensearch_username) != bool(settings.opensearch_password):
        raise ValueError("OpenSearch username and password must be configured together")
    local = host in ("localhost", "127.0.0.1", "::1")
    if url.scheme != "https" and (not local or settings.opensearch_username or settings.opensearch_password):
        raise ValueError("OpenSearch requires TLS for remote endpoints and credentials")
    if url.scheme == "https" and not settings.opensearch_verify_certs:
        raise ValueError("OpenSearch TLS certificate verification is required")


def validate_log_search_response(result: dict, tenant_id: str, service_name: str, limit: int, window=None) -> dict:
    """Never return a cross-tenant or cross-service document from an upstream read."""
    if not isinstance(result, dict):
        raise ValueError("Invalid OpenSearch response")
    hits_container = result.get("hits")
    if not isinstance(hits_container, dict) or not isinstance(hits_container.get("hits"), list):
        raise ValueError("Invalid OpenSearch response")
    hits = hits_container["hits"]
    if len(hits) > limit:
        raise ValueError("OpenSearch returned more hits than requested")
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict):
            raise ValueError("OpenSearch hit missing source")
        source = hit["_source"]
        tenant = source.get("tenant")
        resource = source.get("resource")
        attrs = resource.get("attributes") if isinstance(resource, dict) else None
        if (
            not isinstance(tenant, dict)
            or tenant.get("id") != tenant_id
            or not isinstance(attrs, dict)
            or attrs.get("service.name") != service_name
        ):
            raise ValueError("OpenSearch hit violates tenant or service scope")
        if window is not None:
            timestamp = source.get("@timestamp")
            if not isinstance(timestamp, str):
                raise ValueError("OpenSearch hit missing timestamp")
            try:
                observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("OpenSearch hit has invalid timestamp") from exc
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError("OpenSearch hit has unzoned timestamp")
            if not window.start.astimezone(timezone.utc) <= observed.astimezone(timezone.utc) <= window.end.astimezone(timezone.utc):
                raise ValueError("OpenSearch hit violates requested time window")
    return result


async def search_logs(tenant_id: str, req: LogSearchRequest) -> dict:
    # Validate tenant and build the bounded query before opening any client.
    # Snapshot and revalidate once: query and response checks must use identical filters.
    validated_req = LogSearchRequest.model_validate(req.model_dump())
    query = make_log_query(tenant_id, validated_req)
    validate_opensearch_transport()
    # Lazy import allows local unit tests without connecting to OpenSearch.
    from opensearchpy import AsyncOpenSearch

    auth = (
        (settings.opensearch_username, settings.opensearch_password)
        if settings.opensearch_username else None
    )
    client = AsyncOpenSearch(
        hosts=[settings.opensearch_url],
        http_auth=auth,
        verify_certs=settings.opensearch_verify_certs,
        ca_certs=settings.opensearch_ca_certs,
    )
    try:
        result = await client.search(
            index=settings.opensearch_logs_index,
            body=query,
            request_timeout=10,
        )
        return validate_log_search_response(result, tenant_id, validated_req.service_name, validated_req.limit, validated_req.window)
    finally:
        await client.close()
