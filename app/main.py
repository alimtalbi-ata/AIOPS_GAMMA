from datetime import timedelta
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_tenant_session
from app.models import Evidence, InboxEvent, OutboxEvent, ServiceBinding
from app.opensearch_adapter import search_logs
from app.schemas import AlertPayload, BindingIn, EvidenceIn, LogSearchRequest
from app.security import Principal, internal_principal
from app.settings import settings

app = FastAPI(title="AIOPS_GAMMA", version="0.1.0")

async def tenant_session(principal: Principal = Depends(internal_principal)):
    """Bind every protected tenant DB session to the verified principal."""
    async for session in get_tenant_session(principal.tenant_id):
        yield session



@app.middleware("http")
async def prevent_tenant_api_caching(request, call_next):
    """Apply no-store to tenant API responses, including rejected requests."""
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/health/live":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/health/live")
async def live():
    return {"status": "ok"}


@app.get("/api/v1/demo/correlation")
async def demo_correlation():
    """Public, static synthetic demo; never touches tenants, IdP or database."""
    from app.demo import synthetic_correlation_demo
    return synthetic_correlation_demo()


@app.get("/api/v1/demo/investigation")
async def demo_investigation():
    """Public fixed synthetic evidence join; no tenant or upstream access."""
    from app.demo import synthetic_investigation_demo
    return synthetic_investigation_demo()


@app.post("/api/v1/observability/logs/search")
async def logs(req: LogSearchRequest, response: Response, principal: Principal = Depends(internal_principal)):
    response.headers["Cache-Control"] = "no-store"
    if not settings.enable_opensearch:
        raise HTTPException(503, "OpenSearch adapter disabled", headers={"Cache-Control": "no-store"})
    # Tenant membership alone does not authorize access to every service.
    # Grants must be attested by the gateway in the signed assertion.
    if req.service_name not in principal.log_service_grants:
        raise HTTPException(403, "Service log access denied", headers={"Cache-Control": "no-store"})
    if req.window.end - req.window.start > timedelta(hours=settings.max_query_hours):
        raise HTTPException(422, "Time window exceeds policy", headers={"Cache-Control": "no-store"})
    try:
        return await search_logs(str(principal.tenant_id), req)
    except Exception as exc:
        # Do not expose backend URLs, credentials, index names, or raw client errors.
        raise HTTPException(502, "OpenSearch query failed", headers={"Cache-Control": "no-store"}) from exc


@app.post("/api/v1/observability/metrics/query")
async def metrics(principal: Principal = Depends(internal_principal)):
    raise HTTPException(501, "Tenant-scoped PromQL builder not yet implemented")


def alert_duplicate_response(previous: InboxEvent, payload: dict) -> dict:
    """Idempotent retry is safe only when the deduplication key has identical content."""
    if previous.payload != payload:
        raise HTTPException(409, "Alert event identity already exists with different payload")
    return {"id": str(previous.id), "duplicate": True}


@app.post("/api/v1/integrations/opensearch/alerts")
async def alerts(
    req: AlertPayload, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(tenant_session),
):
    if not settings.enable_alert_ingestion:
        raise HTTPException(503, "Alert ingestion disabled")
    tenant = principal.tenant_id
    payload = req.model_dump(mode="json")
    previous = await session.scalar(select(InboxEvent).where(
        InboxEvent.tenant_id == tenant,
        InboxEvent.source == req.source,
        InboxEvent.external_event_id == req.external_event_id,
    ))
    if previous:
        return alert_duplicate_response(previous, payload)
    event = InboxEvent(
        tenant_id=tenant, source=req.source,
        external_event_id=req.external_event_id,
        payload=payload,
    )
    try:
        session.add(event)
        await session.flush()
        session.add(OutboxEvent(
            tenant_id=tenant, event_type=f"observability.alert.{req.status}",
            aggregate_id=req.service_name, payload=payload
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
            return alert_duplicate_response(previous, payload)
        raise


@app.post("/api/v1/topology/bindings", status_code=201)
async def add_binding(
    req: BindingIn, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(tenant_session),
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
    session: AsyncSession = Depends(tenant_session),
):
    rows = (await session.scalars(
        select(ServiceBinding).where(ServiceBinding.tenant_id == principal.tenant_id).limit(500)
    )).all()
    return [{"id": str(row.id), "cmdb_service_id": str(row.cmdb_service_id),
             "otel_service_name": row.otel_service_name, "environment": row.environment}
            for row in rows]


def validate_incident_resource_id(incident_id: str) -> str:
    """Reject noncanonical resource identifiers before any evidence database access."""
    import unicodedata
    if (not 1 <= len(incident_id) <= 255 or incident_id != incident_id.strip()
            or unicodedata.normalize("NFC", incident_id) != incident_id
            or any(ord(ch) < 32 or ord(ch) == 127
                   or 0xD800 <= ord(ch) <= 0xDFFF
                   or unicodedata.category(ch) in ("Cc", "Cf") for ch in incident_id)
            or "\\" in incident_id or "/" in incident_id
            or "?" in incident_id or "#" in incident_id or incident_id == "*"):
        raise HTTPException(422, "Invalid incident resource identifier")
    return incident_id


@app.post("/api/v1/incidents/{incident_id}/evidence", status_code=201)
async def add_evidence(
    incident_id: str, req: EvidenceIn, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(tenant_session),
):
    validate_incident_resource_id(incident_id)
    if incident_id not in principal.evidence_incident_grants:
        raise HTTPException(403, "Incident evidence access denied", headers={"Cache-Control": "no-store"})
    obj = Evidence(
        tenant_id=principal.tenant_id, incident_id=incident_id, **req.model_dump()
    )
    session.add(obj)
    await session.commit()
    return {"id": str(obj.id)}


@app.get("/api/v1/incidents/{incident_id}/evidence")
async def list_evidence(
    incident_id: str, principal: Principal = Depends(internal_principal),
    session: AsyncSession = Depends(tenant_session),
):
    validate_incident_resource_id(incident_id)
    if incident_id not in principal.evidence_incident_grants:
        raise HTTPException(403, "Incident evidence access denied", headers={"Cache-Control": "no-store"})
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
    req: CorrelationPreview, response: Response,
    principal: Principal = Depends(internal_principal),
):
    # Incident signals must not be cached by browsers or shared proxies.
    response.headers["Cache-Control"] = "no-store"
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
    req: LLMKPIRequest, response: Response,
    principal: Principal = Depends(internal_principal),
):
    # Per-tenant model telemetry and costs must never be cached by shared
    # proxies or browsers, even when the samples are caller-supplied.
    response.headers["Cache-Control"] = "no-store"
    try:
        return calculate_llm_kpis(req, principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Read-only SLO evaluation on caller-supplied model samples.
from app.reused.llm_slo import LLMSLOPreviewRequest, evaluate_llm_slo_preview


@app.post("/api/v1/observability/llm/slo/preview")
async def llm_slo_preview(
    req: LLMSLOPreviewRequest, response: Response,
    principal: Principal = Depends(internal_principal),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return evaluate_llm_slo_preview(req, principal.tenant_id)
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
