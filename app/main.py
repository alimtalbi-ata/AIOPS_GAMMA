from datetime import timedelta
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Evidence, InboxEvent, OutboxEvent, ServiceBinding
from app.opensearch_adapter import search_logs
from app.schemas import AlertPayload, BindingIn, EvidenceIn, LogSearchRequest
from app.security import Principal, internal_principal
from app.settings import settings

app = FastAPI(title="AIOPS_GAMMA", version="0.1.0")


@app.get("/api/v1/health/live")
async def live():
    return {"status": "ok"}


@app.post("/api/v1/observability/logs/search")
async def logs(req: LogSearchRequest, principal: Principal = Depends(internal_principal)):
    if not settings.enable_opensearch:
        raise HTTPException(503, "OpenSearch adapter disabled")
    if req.window.end - req.window.start > timedelta(hours=settings.max_query_hours):
        raise HTTPException(422, "Time window exceeds policy")
    return await search_logs(str(principal.tenant_id), req)


@app.post("/api/v1/observability/metrics/query")
async def metrics(principal: Principal = Depends(internal_principal)):
    raise HTTPException(501, "Tenant-scoped PromQL builder not yet implemented")


@app.post("/api/v1/integrations/opensearch/alerts")
async def alerts(
    req: AlertPayload, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(get_session),
):
    if not settings.enable_alert_ingestion:
        raise HTTPException(503, "Alert ingestion disabled")
    tenant = principal.tenant_id
    previous = await session.scalar(select(InboxEvent).where(
        InboxEvent.tenant_id == tenant,
        InboxEvent.source == req.source,
        InboxEvent.external_event_id == req.external_event_id,
    ))
    if previous:
        return {"id": str(previous.id), "duplicate": True}
    event = InboxEvent(
        tenant_id=tenant, source=req.source,
        external_event_id=req.external_event_id,
        payload=req.model_dump(mode="json"),
    )
    try:
        session.add(event)
        await session.flush()
        session.add(OutboxEvent(
            tenant_id=tenant, event_type=f"observability.alert.{req.status}",
            aggregate_id=req.service_name, payload=req.model_dump(mode="json")
        ))
        await session.commit()
        return {"id": str(event.id), "duplicate": False}
    except IntegrityError:
        await session.rollback()
        previous = await session.scalar(select(InboxEvent).where(
            InboxEvent.tenant_id == tenant,
            InboxEvent.source == req.source,
            InboxEvent.external_event_id == req.external_event_id,
        ))
        if previous:
            return {"id": str(previous.id), "duplicate": True}
        raise


@app.post("/api/v1/topology/bindings", status_code=201)
async def add_binding(
    req: BindingIn, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(get_session),
):
    obj = ServiceBinding(tenant_id=principal.tenant_id, **req.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Binding already exists") from exc
    return {"id": str(obj.id)}


@app.get("/api/v1/topology/bindings")
async def list_bindings(
    principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(ServiceBinding).where(ServiceBinding.tenant_id == principal.tenant_id).limit(500)
    )).all()
    return [{"id": str(row.id), "cmdb_service_id": str(row.cmdb_service_id),
             "otel_service_name": row.otel_service_name, "environment": row.environment}
            for row in rows]


@app.post("/api/v1/incidents/{incident_id}/evidence", status_code=201)
async def add_evidence(
    incident_id: str, req: EvidenceIn, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(get_session),
):
    obj = Evidence(
        tenant_id=principal.tenant_id, incident_id=incident_id, **req.model_dump()
    )
    session.add(obj)
    await session.commit()
    return {"id": str(obj.id)}


@app.get("/api/v1/incidents/{incident_id}/evidence")
async def list_evidence(
    incident_id: str, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.scalars(
        select(Evidence).where(Evidence.tenant_id == principal.tenant_id,
                               Evidence.incident_id == incident_id).limit(500)
    )).all()
    return [{"id": str(e.id), "investigation_id": str(e.investigation_id),
             "source_type": e.source_type, "source_ref": e.source_ref,
             "summary": e.summary, "observed_at": e.observed_at.isoformat()}
            for e in rows]
