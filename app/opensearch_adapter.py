from app.schemas import LogSearchRequest
from app.settings import settings


def make_log_query(tenant_id: str, req: LogSearchRequest) -> dict:
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


async def search_logs(tenant_id: str, req: LogSearchRequest) -> dict:
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
        return await client.search(
            index=settings.opensearch_logs_index,
            body=make_log_query(tenant_id, req),
            request_timeout=10,
        )
    finally:
        await client.close()
