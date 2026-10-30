"""HTTP surface for proactive watch."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import ROOT
from . import alerts as alert_ops
from . import anticipation, integrations, scheduler
from .demo import TENANT, seed_demo
from .engine import ProactiveEngine
from .governance import KillSwitch, ModelRegistry, ValidationGate, privacy_review_proactive
from .models import (
    Alert,
    CostEntry,
    Forecast,
    MonitoringPlan,
    Scope,
    TenantPreferences,
    new_id,
    now_iso,
)
from .notifications import preferences_payload
from .observability import metrics_snapshot
from .ops import BlueGreen, JobQueue, LocalObjectStore, PostgresMirror, QuotaManager
from .store import ProactiveStore
from ..production.config import get_settings
from ..production.store_pg import build_store

settings = get_settings()
store = build_store(settings.platform.postgres_dsn, str(ROOT / "runtime" / "proactive.db"))
if not store.list_scopes(TENANT) and settings.mode != "production":
    seed_demo(store)
engine = ProactiveEngine(store, live_channels=settings.mode == 'production')
router = APIRouter(prefix="/api/watch", tags=["proactive"])


class ScopeRequest(BaseModel):
    name: str
    kind: str = "aoi"
    region: str = ""
    center: tuple[float, float]
    bbox: tuple[float, float, float, float]
    asset_class: str = "insurance"
    change_types: list[str] = Field(default_factory=lambda: ["flood"])
    cadence: str = "weekly"
    priority: int = 3
    subscription_tier: str = "weekly"
    freshness_slo_hours: float = 168
    recipients: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant: str = TENANT


class PlanRequest(BaseModel):
    cadence: str | None = None
    sources: list[str] | None = None
    recipients: list[str] | None = None
    sla_hours: float | None = None
    quiet_hours: tuple[int, int] | None = None
    digest: str | None = None
    budget_eur_per_month: float | None = None
    paused: bool | None = None
    kill_switch: bool | None = None
    first_n_alerts_require_analyst: int | None = None
    channels: list[str] | None = None


class ActionRequest(BaseModel):
    action: Literal["acknowledge", "assign", "investigate", "resolve", "dismiss"]
    actor: str = "analyst"
    note: str = ""
    assignee: str | None = None
    reason: str | None = None
    proposal_id: str | None = None


class ProposalDecision(BaseModel):
    actor: str = "analyst"
    reason: str = ""


class BulkRequest(BaseModel):
    ids: list[str]
    action: Literal["acknowledge", "assign", "investigate", "resolve", "dismiss"]
    actor: str = "analyst"
    assignee: str | None = None
    reason: str | None = None


class ObservationRequest(BaseModel):
    scopeId: str
    observation: dict[str, Any]
    modelVersion: str = "gr-changenet-1.4.2"


class PrefsRequest(BaseModel):
    channels: list[str] = Field(default_factory=lambda: ["email", "slack"])
    quiet_hours: tuple[int, int] | None = (22, 7)
    digest: str = "instant"
    language: str = "en"
    alert_budget_per_day: int = 8
    recipients: list[dict] = Field(default_factory=list)
    escalation_minutes: int = 30
    webhook_url: str | None = None
    paused: bool = False
    kill_switch: bool = False


class ForecastRequest(BaseModel):
    region: str
    hazard: str = "flood"
    probability: float = 0.5
    rainfall_mm: float = 0.0
    wind_kmh: float = 0.0
    river_level_m: float = 0.0
    uncertainty: float = 0.2
    valid_from: str | None = None
    valid_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRequest(BaseModel):
    name: str
    version: str
    metrics: dict[str, float] = Field(default_factory=dict)


class ValidationRequest(BaseModel):
    analyst: str = "A. Weber"
    decision: str = "validated"
    note: str = ""


def _scope_or_404(scope_id: str) -> Scope:
    scope = store.get_scope(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail=f"unknown scope {scope_id}")
    return scope


def _alert_or_404(alert_id: str) -> Alert:
    alert = store.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"unknown alert {alert_id}")
    return alert


@router.get("/overview")
def overview(tenant: str = TENANT) -> dict:
    forecasts = store.list_forecasts()
    scopes = store.list_scopes(tenant)
    plans = [store.get_plan(scope.id) or MonitoringPlan(scope_id=scope.id, cadence=scope.cadence) for scope in scopes]
    watch = engine.watch(tenant, forecasts)
    dashboard = engine.dashboard(tenant)
    from .governance import KillSwitch, alert_quality, governance_snapshot

    return {
        "generatedAt": now_iso(),
        "tenant": tenant,
        "mode": "live",
        "shadowMode": settings.mode != "production",
        "disclaimer": "Live tenant data from the configured store. Human review is mandatory.",
        "scopes": [scope.to_dict() for scope in scopes],
        "plans": [plan.to_dict() for plan in plans],
        "alerts": [alert.to_dict() for alert in store.list_alerts(tenant)],
        "incidents": [incident.to_dict() for incident in store.list_incidents(tenant)],
        "forecasts": [forecast.to_dict() for forecast in forecasts],
        "acquisitions": [acquisition.to_dict() for acquisition in store.list_acquisitions(limit=200)],
        "baselines": [baseline.to_dict() for scope in scopes for baseline in store.list_baselines(scope.id)],
        "watch": watch,
        "coverage": watch["coverage"],
        "blindSpots": watch["blindSpots"],
        "freshness": watch["freshness"],
        "calendar": {scope.id: scheduler.calendar(store, scope.id) for scope in scopes},
        "dashboard": dashboard,
        "pilot": engine.pilot_report(tenant),
        "digest": alert_ops.digest(store, tenant),
        "quality": alert_quality(store, tenant),
        "governance": governance_snapshot(store, tenant),
        "models": [model.to_dict() for model in store.list_models()],
        "preferences": preferences_payload(store.get_preferences(tenant)),
        "notifications": engine.notifications.outbox(tenant),
        "costs": {"summary": scheduler.cost_report(store, tenant, days=30), "byScope": [{"scopeId": scope.id, "name": scope.name, "totalEur": store.total_cost(tenant, scope_id=scope.id)} for scope in scopes]},
        "killSwitch": KillSwitch(store).active(tenant),
        "audit": {"events": store.audit_events(tenant, 100), "verified": store.verify_audit(tenant)},
    }


@router.get("/scopes")
def list_scopes(tenant: str | None = TENANT) -> list[dict]:
    return [scope.to_dict() for scope in store.list_scopes(tenant)]


@router.post("/scopes", status_code=201)
def create_scope(request: ScopeRequest) -> dict:
    scope = Scope(
        id=new_id("scope"),
        tenant=request.tenant,
        name=request.name,
        kind=request.kind,
        region=request.region,
        center=request.center,
        bbox=request.bbox,
        asset_class=request.asset_class,
        change_types=request.change_types,
        cadence=request.cadence,
        priority=request.priority,
        subscription_tier=request.subscription_tier,
        freshness_slo_hours=request.freshness_slo_hours,
        recipients=request.recipients,
        tags=request.tags,
        metadata=request.metadata,
    )
    store.save_scope(scope)
    store.save_plan(MonitoringPlan(scope_id=scope.id, cadence=scope.cadence, recipients=request.recipients))
    store.audit(scope.tenant, "scope.created", actor="api", detail={"scope": scope.id})
    return scope.to_dict()


@router.get("/scopes/{scope_id}")
def get_scope(scope_id: str) -> dict:
    scope = _scope_or_404(scope_id)
    plan = store.get_plan(scope.id)
    return {"scope": scope.to_dict(), "plan": plan.to_dict() if plan else None, "readiness": scheduler.readiness(store, scope, plan or MonitoringPlan(scope_id=scope.id))}


@router.patch("/scopes/{scope_id}/plan")
def update_plan(scope_id: str, request: PlanRequest) -> dict:
    scope = _scope_or_404(scope_id)
    plan = store.get_plan(scope_id) or MonitoringPlan(scope_id=scope_id, cadence=scope.cadence)
    payload = plan.to_dict()
    for key, value in request.model_dump(exclude_none=True).items():
        payload[key] = value
    updated = MonitoringPlan.from_dict(payload)
    updated.updated_at = now_iso()
    store.save_plan(updated)
    store.audit(scope.tenant, "plan.updated", actor="api", detail=request.model_dump(exclude_none=True))
    return updated.to_dict()


@router.post("/scopes/{scope_id}/pause")
def pause_scope(scope_id: str, reason: str = "", actor: str = "api") -> dict:
    scope = _scope_or_404(scope_id)
    store.set_scope_status(scope_id, "paused")
    plan = store.get_plan(scope_id)
    if plan:
        plan.paused = True
        store.save_plan(plan)
    store.audit(scope.tenant, "scope.paused", actor=actor, detail={"scope": scope_id, "reason": reason})
    return {"scope": scope_id, "status": "paused", "reason": reason}


@router.post("/scopes/{scope_id}/resume")
def resume_scope(scope_id: str, reason: str = "", actor: str = "api") -> dict:
    scope = _scope_or_404(scope_id)
    store.set_scope_status(scope_id, "active")
    plan = store.get_plan(scope_id)
    if plan:
        plan.paused = False
        plan.kill_switch = False
        store.save_plan(plan)
    store.audit(scope.tenant, "scope.resumed", actor=actor, detail={"scope": scope_id, "reason": reason})
    return {"scope": scope_id, "status": "active", "reason": reason}


@router.post("/scopes/{scope_id}/watch-now")
def watch_now(scope_id: str, actor: str = "analyst") -> dict:
    _scope_or_404(scope_id)
    acquisition = scheduler.watch_now(store, scope_id, actor=actor)
    if acquisition is None:
        raise HTTPException(status_code=409, detail="scope paused, kill switch active, or budget cap reached")
    return acquisition.to_dict()


@router.get("/coverage")
def coverage(tenant: str = TENANT) -> dict:
    return {
        "coverage": scheduler.coverage(store, tenant),
        "blindSpots": scheduler.blind_spots(store, tenant),
        "freshness": scheduler.freshness_slo(store, tenant),
    }


@router.get("/scopes/{scope_id}/calendar")
def calendar(scope_id: str, days: int = 14) -> list[dict]:
    _scope_or_404(scope_id)
    return scheduler.calendar(store, scope_id, days=days)


@router.get("/alerts")
def list_alerts(tenant: str = TENANT, status: str | None = None, scope_id: str | None = None) -> list[dict]:
    return [alert.to_dict() for alert in store.list_alerts(tenant, scope_id, status)]


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict:
    alert = _alert_or_404(alert_id)
    return {
        "alert": alert.to_dict(),
        "explain": engine.explain(alert_id),
        "sla": alert_ops.sla_status(alert),
        "narrative": alert_ops.mobile_card(alert),
    }


@router.post("/alerts/{alert_id}/status-update")
def status_update(alert_id: str, author: str, message: str) -> dict:
    alert = _alert_or_404(alert_id)
    update = alert_ops.customer_status_update(alert, author=author, message=message)
    store.audit(alert.tenant, "alert.customer-status", alert_id=alert.id, actor=author, detail={"message": message})
    return update


@router.post("/alerts/{alert_id}/action")
def alert_action(alert_id: str, request: ActionRequest) -> dict:
    _alert_or_404(alert_id)
    if request.actor in {"agent", "agent-approved"}:
        from .proposals import ProposalError, ProposalStore

        if not request.proposal_id:
            raise HTTPException(status_code=400, detail="agent-origin actions require proposal_id")
        try:
            proposal = ProposalStore(store).get(request.proposal_id)
        except ProposalError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if proposal.alert_id != alert_id or proposal.status != "approved":
            raise HTTPException(status_code=403, detail="proposal is not approved for this alert")
    try:
        return engine.review(alert_id, request.action, actor=request.actor, note=request.note, assignee=request.assignee, reason=request.reason)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/alerts/bulk")
def alert_bulk(request: BulkRequest) -> dict:
    try:
        return alert_ops.bulk_action(store, request.ids, request.action, actor=request.actor, assignee=request.assignee, reason=request.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/incidents")
def incidents(tenant: str = TENANT, status: str | None = None) -> list[dict]:
    return [incident.to_dict() for incident in store.list_incidents(tenant, status)]


@router.get("/incidents/{incident_id}")
def incident(incident_id: str) -> dict:
    row = store.get_incident(incident_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown incident")
    return row.to_dict()


@router.get("/incidents/{incident_id}/view")
def incident_view(incident_id: str) -> dict:
    try:
        return engine.incident_view(incident_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown incident") from exc


@router.get("/scopes/{scope_id}/trend")
def scope_trend(scope_id: str) -> dict:
    _scope_or_404(scope_id)
    return engine.scope_trend(scope_id)


@router.get("/incidents/{incident_id}/timeline")
def timeline(incident_id: str) -> list[dict]:
    try:
        return alert_ops.incident_timeline(store, incident_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown incident") from exc


@router.get("/dashboard")
def dashboard(tenant: str = TENANT) -> dict:
    return engine.dashboard(tenant)


@router.get("/pilot")
def pilot(tenant: str = TENANT) -> dict:
    return engine.pilot_report(tenant)


@router.get("/digest")
def digest(tenant: str = TENANT, hours: int = 24) -> dict:
    return alert_ops.digest(store, tenant, hours=hours)


@router.get("/governance")
def governance(tenant: str = TENANT) -> dict:
    return engine.dashboard(tenant)["governance"]


@router.get("/privacy")
def privacy() -> dict:
    return privacy_review_proactive()


@router.get("/preferences")
def get_preferences(tenant: str = TENANT) -> dict:
    return preferences_payload(store.get_preferences(tenant))


@router.put("/preferences")
def put_preferences(request: PrefsRequest, tenant: str = TENANT) -> dict:
    prefs = TenantPreferences(tenant=tenant, **request.model_dump())
    store.save_preferences(prefs)
    store.audit(tenant, "preferences.updated", actor="api")
    return preferences_payload(prefs)


@router.get("/notifications/outbox")
def outbox(tenant: str = TENANT) -> list[dict]:
    return engine.notifications.outbox(tenant)


@router.post("/notifications/{notification_id}/retry")
def notification_retry(notification_id: str) -> dict:
    try:
        return engine.notifications.retry_dead(notification_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown notification") from exc


@router.get("/forecasts")
def forecasts() -> list[dict]:
    return [forecast.to_dict() for forecast in store.list_forecasts()]


@router.post("/forecasts", status_code=201)
def create_forecast(request: ForecastRequest) -> dict:
    payload = request.model_dump()
    payload["issuedAt"] = now_iso()
    payload["validFrom"] = request.valid_from or now_iso()
    payload["validTo"] = request.valid_to or now_iso()
    forecast = anticipation.ingest_forecast(payload)
    store.save_forecast(forecast)
    store.audit(TENANT, "forecast.ingested", actor="api", detail={"id": forecast.id, "region": forecast.region})
    return forecast.to_dict()


@router.get("/watchlist")
def watchlist(tenant: str = TENANT) -> list[dict]:
    return anticipation.pre_event_watchlist(store, tenant, store.list_forecasts())


@router.post("/simulate/{scope_id}")
def simulate(scope_id: str, water_level_m: float = 3.0) -> dict:
    scope = _scope_or_404(scope_id)
    return anticipation.simulate_scenario(scope, water_level_m=water_level_m)


@router.post("/observations")
def ingest_observation(request: ObservationRequest) -> dict:
    try:
        return engine.ingest(request.scopeId, request.observation, model_version=request.modelVersion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown scope") from exc


@router.post("/tick")
def tick() -> dict:
    return engine.run_tick(tenant=TENANT, forecasts=store.list_forecasts())


@router.get("/costs")
def costs(tenant: str = TENANT, days: int = 30) -> dict:
    return scheduler.cost_report(store, tenant, days=days)


@router.get("/audit")
def audit(tenant: str = TENANT) -> dict:
    return {"events": store.audit_events(tenant, 200), "verification": store.verify_audit(tenant)}


@router.post("/kill-switch")
def kill_switch(active: bool = True, tenant: str = TENANT) -> dict:
    return KillSwitch(store).set(tenant, active, actor="api")


@router.post("/scopes/{scope_id}/validate")
def validate(scope_id: str, alert_id: str, request: ValidationRequest) -> dict:
    _scope_or_404(scope_id)
    gate = ValidationGate(store)
    record = gate.record(scope_id, alert_id, request.analyst, request.decision, request.note)
    return record.to_dict()


@router.post("/models/register")
def register_model(request: ModelRequest) -> dict:
    entry = ModelRegistry(store).register(request.name, request.version, metrics=request.metrics)
    return entry.to_dict()


@router.post("/models/deploy")
def deploy_model(request: ModelRequest) -> dict:
    entry = ModelRegistry(store).deploy(request.name, request.version, metrics=request.metrics)
    return entry.to_dict()


@router.post("/models/{name}/rollback")
def rollback_model(name: str) -> dict:
    try:
        return ModelRegistry(store).rollback(name).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/integrations")
def integration_manifest() -> dict:
    return integrations.integration_manifest()


@router.post("/alerts/{alert_id}/handoff/{target}")
def handoff(alert_id: str, target: str) -> dict:
    alert = _alert_or_404(alert_id)
    if target in {"assessment", "claim", "inspection", "dispatch"}:
        return alert_ops.handoff_payload(alert, target)
    return integrations.dispatch_system(target, alert)


@router.get("/scopes/{scope_id}/qgis")
def qgis(scope_id: str) -> str:
    scope = _scope_or_404(scope_id)
    return integrations.qgis_monitoring_project(scope.tenant, [scope], store.list_alerts(scope.tenant))


@router.post("/acquisitions/{acquisition_id}/approve")
def approve_acquisition(acquisition_id: str, actor: str = "ops") -> dict:
    try:
        return scheduler.approve_acquisition(store, acquisition_id, actor=actor).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown acquisition") from exc


@router.get("/jobs")
def jobs(queue: str | None = None) -> dict:
    from ..production.queue import RedisJobQueue, QueueUnavailable

    try:
        if get_settings().platform.redis_url:
            return RedisJobQueue().stats(queue)
    except QueueUnavailable:
        pass
    return JobQueue(store).stats(queue)


@router.get("/objects")
def objects(prefix: str = "") -> list[dict]:
    return LocalObjectStore(ROOT / "runtime" / "objects").list(prefix)


@router.get("/metrics")
def metrics() -> dict:
    return metrics_snapshot()


@router.get("/quotas")
def quotas(tenant: str = TENANT) -> dict:
    return QuotaManager(store).check(tenant)


@router.get("/deployment")
def deployment() -> dict:
    return BlueGreen(store).current()


@router.post("/deployment/promote")
def promote(version: str) -> dict:
    return BlueGreen(store).promote(version)


@router.post("/deployment/rollback")
def deployment_rollback() -> dict:
    return BlueGreen(store).rollback()


@router.get("/postgres-mirror")
def postgres_mirror(tenant: str = TENANT) -> dict:
    return PostgresMirror().sync(store, tenant)


@router.get("/quality")
def quality(tenant: str = TENANT) -> dict:
    from .governance import alert_quality

    return alert_quality(store, tenant)



# ---------------------------------------------------------------- insights
class FeedbackRequest(BaseModel):
    verdict: str
    note: str = ""
    actor: str = "analyst"


@router.get("/since")
def since(tenant: str = TENANT, ts: str | None = None) -> dict:
    from .insights import what_changed

    return what_changed(store, tenant, since=ts)


@router.get("/drift")
def drift(tenant: str = TENANT, days: int = 14) -> dict:
    from .insights import drift as compute_drift

    return compute_drift(store, tenant, days=days)


@router.get("/notifications/analytics")
def notifications_analytics(tenant: str = TENANT) -> dict:
    from .insights import notification_analytics

    return notification_analytics(store, tenant)


@router.post("/alerts/{alert_id}/feedback")
def alert_feedback(alert_id: str, request: FeedbackRequest) -> dict:
    from .insights import record_feedback

    _alert_or_404(alert_id)
    try:
        return record_feedback(store, alert_id, request.verdict, note=request.note, actor=request.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/alerts/{alert_id}/feedback")
def alert_feedback_list(alert_id: str) -> dict:
    from .insights import alert_feedback as list_feedback

    _alert_or_404(alert_id)
    return {"alertId": alert_id, "feedback": list_feedback(store, alert_id)}


@router.get("/feedback/summary")
def feedback_summary(tenant: str = TENANT) -> dict:
    from .insights import feedback_summary as summary

    return summary(store, tenant)


@router.get("/proposals")
def proposals(tenant: str = TENANT, status: str | None = None) -> dict:
    from .proposals import ProposalStore

    items = ProposalStore(store).pending(tenant)
    if status and status != "pending":
        items = []
    return {"tenant": tenant, "proposals": [item.to_dict() for item in items]}


@router.post("/proposals/{proposal_id}/approve")
def proposal_approve(proposal_id: str, request: ProposalDecision) -> dict:
    from .proposals import ProposalError, ProposalStore

    try:
        return ProposalStore(store).approve(proposal_id, actor=request.actor)
    except ProposalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/reject")
def proposal_reject(proposal_id: str, request: ProposalDecision) -> dict:
    from .proposals import ProposalError, ProposalStore

    try:
        return ProposalStore(store).reject(proposal_id, actor=request.actor, reason=request.reason)
    except ProposalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/undo")
def proposal_undo(proposal_id: str, request: ProposalDecision) -> dict:
    from .proposals import ProposalError, ProposalStore

    try:
        return ProposalStore(store).undo(proposal_id, actor=request.actor)
    except ProposalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------- production
class LiveAgentRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    tenant: str = TENANT
    context: dict = Field(default_factory=dict)


@router.get("/production/worker/health")
def worker_health() -> dict:
    from .insights import worker_health as read_heartbeat

    return read_heartbeat(str(ROOT / "runtime" / "worker-heartbeat.json"))


@router.get("/production/doctor")
def production_doctor() -> dict:
    from ..production.config import doctor

    return doctor()


@router.get("/production/agent/health")
def agent_health() -> dict:
    from ..production.agent import PROMPT_VERSION
    from ..production.agent_backend import status
    from ..production.config import get_settings

    settings = get_settings()
    runtime = status(settings)
    prompt = PROMPT_VERSION
    if runtime["resolved"] == "openjiuwen":
        from ..production.openjiuwen_runtime import PROMPT_VERSION as OPENJIUWEN_PROMPT

        prompt = OPENJIUWEN_PROMPT
    return {
        "configured": settings.llm.configured,
        "backend": runtime["resolved"],
        "configuredBackend": runtime["configured"],
        "openjiuwenAvailable": runtime["openjiuwenAvailable"],
        "openjiuwenDetail": runtime["openjiuwenDetail"],
        "model": settings.llm.model or None,
        "promptVersion": prompt,
        "settings": settings.llm.safe(),
    }


@router.post("/production/agent/chat")
async def agent_chat(request: LiveAgentRequest) -> dict:
    from ..production.agent import AgentUnavailable
    from ..production.agent_backend import select
    from ..production.config import get_settings
    from ..production.openjiuwen_runtime import OpenJiuwenUnavailable

    backend, _resolved = select(engine, get_settings())
    try:
        return await backend.chat(request.message, tenant=request.tenant, history=request.history, context=request.context)
    except (AgentUnavailable, OpenJiuwenUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"agent backend error: {exc}") from exc


@router.post("/production/agent/stream")
async def agent_stream(request: LiveAgentRequest):
    from fastapi.responses import StreamingResponse

    from ..production.agent import AgentUnavailable
    from ..production.agent_backend import select
    from ..production.config import get_settings
    from ..production.openjiuwen_runtime import OpenJiuwenUnavailable

    backend, _resolved = select(engine, get_settings())

    async def events():
        try:
            async for event in backend.stream(request.message, tenant=request.tenant, history=request.history, context=request.context):
                yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
        except (AgentUnavailable, OpenJiuwenUnavailable) as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'detail': f'agent stream error: {exc}'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/production/inference/health")
def inference_health() -> dict:
    from ..production.inference import service_health

    return service_health()


@router.post("/production/inference/score")
def inference_score(payload: dict) -> dict:
    from ..production.inference import OnnxDamageModel

    try:
        model = OnnxDamageModel()
        rows = payload.get("rows") or []
        return {"ok": True, "probabilities": model.predict(rows), **model.health()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/production/notifications/channels")
def notification_channels() -> dict:
    from ..production.transports import channel_status

    return channel_status()


@router.get("/production/integrations/status")
def integration_status() -> dict:
    from ..production.integrations import status

    return status()


@router.post("/production/integrations/{target}/{alert_id}")
def integration_send(target: str, alert_id: str) -> dict:
    from ..production.integrations import IntegrationUnavailable, dispatch as live_dispatch

    alert = _alert_or_404(alert_id)
    try:
        return live_dispatch(target, alert)
    except IntegrationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/production/imagery/status")
def imagery_status(scenario: str = "ahr-2021-flood") -> dict:
    from ..production.imagery import cache_status

    return cache_status(scenario, ROOT / "runtime" / "imagery")


@router.get("/production/imagery/search")
def imagery_search(bbox: str, start: str, end: str, max_cloud: float = 30) -> dict:
    from ..production.imagery import search_sentinel

    try:
        values = [float(value) for value in bbox.split(",")]
        return {"items": search_sentinel(values, start, end, max_cloud=max_cloud)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/production/imagery/fetch/{scenario_id}")
def imagery_fetch(scenario_id: str) -> dict:
    from ..production.imagery import fetch_scenario

    try:
        return fetch_scenario(scenario_id, ROOT / "runtime" / "imagery")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
