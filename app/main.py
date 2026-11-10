from datetime import timedelta
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response
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


# Reused pure impact estimator from the existing AIOps platform.
# This endpoint does not authorize LIVE operations or remediation.
from pydantic import BaseModel, Field
from app.reused.impact import estimate_impact
from app.reused.policy import RemediationProposal, evaluate as evaluate_policy


class ImpactRequest(BaseModel):
    direct_impact: float = Field(ge=0, le=1)
    redundant_paths: int = Field(ge=0)
    total_paths: int = Field(ge=0)


@app.post("/api/v1/topology/impact/estimate")
async def impact_estimate(
    req: ImpactRequest, principal: Principal = Depends(internal_principal)
):
    try:
        estimate = estimate_impact(
            req.direct_impact, req.redundant_paths, req.total_paths
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "state": estimate.state,
        "score": estimate.score,
        "source": estimate.source,
        "live_remediation_authorized": False,
    }


@app.post("/api/v1/policy/remediation/preview")
async def remediation_preview(
    proposal: RemediationProposal, principal: Principal = Depends(internal_principal)
):
    """Advisory policy evaluation only. Never authorizes effect execution."""
    return evaluate_policy(proposal)


# Pure correlation preview: advisory only; canonical incident ownership remains
# with the existing AIOps Core and ITSM connectors.
from app.reused.correlation import CorrelationPreview, correlate


@app.post("/api/v1/incidents/correlation/preview")
async def correlation_preview(
    req: CorrelationPreview, principal: Principal = Depends(internal_principal)
):
    return correlate(req.signals, str(principal.tenant_id), req.window_seconds)


from app.reused.upstream import ALLOWED_RESOURCES, fetch_canonical


@app.get("/api/v1/canonical/{resource}/snapshot")
async def canonical_snapshot(resource: str, principal: Principal = Depends(internal_principal)):
    """Bounded, read-only provisional upstream adapter; never mutates canonical Core."""
    if resource not in ALLOWED_RESOURCES:
        raise HTTPException(404, "Unknown upstream resource")
    return await fetch_canonical(resource, principal.tenant_id)


# ITIL 4 practice-specific, read-only projection. ITSM remains authority.
from app.reused.itil import ITILPreviewRequest, preview_itil_workflow


@app.post("/api/v1/itil4/workflow/preview")
async def itil_workflow_preview(
    req: ITILPreviewRequest, principal: Principal = Depends(internal_principal)
):
    if req.incident.tenant_id != principal.tenant_id:
        raise HTTPException(403, "Cross-tenant incident rejected")
    try:
        return preview_itil_workflow(req.incident, req.problem, req.change)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Enterprise-specific ITIL 4 priority and incident sync planning: no ITSM writes.
from app.reused.itsm_contract import IncidentSyncPreview, plan_incident_sync


@app.post("/api/v1/itil4/incidents/sync-preview")
async def itsm_sync_preview(
    req: IncidentSyncPreview, principal: Principal = Depends(internal_principal)
):
    try:
        return plan_incident_sync(req, principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# GLPI ticket snapshot: fixed server-side tenant/entity binding, GET only.
from app.reused.glpi_read import read_glpi_incident


@app.get("/api/v1/itil4/glpi/incidents/{ticket_id}/snapshot")
async def glpi_incident_snapshot(
    ticket_id: int, response: Response, principal: Principal = Depends(internal_principal)
):
    # Incident metadata must not be retained by shared gateways or browsers.
    response.headers["Cache-Control"] = "no-store"
    return await read_glpi_incident(principal.tenant_id, ticket_id)


# KPI preview inspired by Sentinel telemetry counters and ArgusLM LLM timings.
# Caller-supplied samples are not trusted as authoritative tenant telemetry.
from app.reused.llm_kpi import LLMKPIRequest, calculate_llm_kpis


@app.post("/api/v1/observability/llm/kpis/preview")
async def llm_kpi_preview(
    req: LLMKPIRequest, principal: Principal = Depends(internal_principal),
):
    try:
        return calculate_llm_kpis(req, principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Typed evidence-linked investigation preview. No agent or tool execution.
from app.reused.investigation import InvestigationPreview, evaluate_investigation


@app.post("/api/v1/incidents/investigation/preview")
async def investigation_preview(
    req: InvestigationPreview, principal: Principal = Depends(internal_principal),
):
    try:
        return evaluate_investigation(req, principal.tenant_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


# Caller-supplied evidence is previewed only; the authenticated tenant is authoritative.
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.reused.evidence import EvidenceInput, normalize as normalize_evidence


class EvidencePreviewRequest(BaseModel):
    items: list[EvidenceInput] = Field(min_length=1, max_length=500)
    max_age_seconds: int = Field(default=3600, ge=1, le=86400)


@app.post("/api/v1/incidents/evidence/preview")
async def evidence_preview(
    req: EvidencePreviewRequest,
    response: Response,
    principal: Principal = Depends(internal_principal),
):
    response.headers["Cache-Control"] = "no-store"
    if any(item.tenant_id != str(principal.tenant_id) for item in req.items):
        raise HTTPException(403, "Cross-tenant evidence rejected")
    try:
        return normalize_evidence(
            req.items, now=datetime.now(timezone.utc),
            max_age_seconds=req.max_age_seconds,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Invalid evidence payload") from exc


# Explicit source-event join; no fuzzy matching, incident mutation, or LIVE actions.
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview as correlation_evidence_join


@app.post("/api/v1/incidents/correlation-evidence/preview")
async def correlation_evidence_preview(
    req: CorrelationEvidencePreview,
    response: Response,
    principal: Principal = Depends(internal_principal),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return correlation_evidence_join(req, str(principal.tenant_id))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Invalid correlation evidence payload") from exc
