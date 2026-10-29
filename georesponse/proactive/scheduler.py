"""Acquisition scheduling, freshness and cost controls.

The scheduler is deliberately dependency-free: a deterministic tick that can run
from cron, a container worker, or an air-gapped import job.  It never downloads
during the stage demo and it never exceeds a tenant's monthly budget.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import (
    Acquisition,
    CostEntry,
    Forecast,
    MonitoringPlan,
    Scope,
    add_hours,
    hours_since,
    new_id,
    now_iso,
    parse_iso,
    utcnow,
)
from .store import ProactiveStore

CADENCE_HOURS = {"6h": 6, "12h": 12, "daily": 24, "weekly": 168, "event": 24 * 30}
SOURCE_COST = {"sentinel-2": 0.0, "sentinel-1": 0.0, "planet": 180.0, "maxar": 950.0, "airbus": 620.0, "drone": 350.0}
SOURCE_RESOLUTION = {"sentinel-2": 10.0, "sentinel-1": 10.0, "planet": 3.0, "maxar": 0.3, "airbus": 0.5, "drone": 0.1}
MAX_ATTEMPTS = 4


def cadence_hours(cadence: str) -> float:
    return float(CADENCE_HOURS.get(cadence, 168))


def forecast_for_scope(scope: Scope, forecasts: list[Forecast]) -> Forecast | None:
    candidates = [f for f in forecasts if f.region.lower() in scope.region.lower() or scope.region.lower() in f.region.lower()]
    if not candidates:
        candidates = forecasts
    return max(candidates, key=lambda f: f.probability) if candidates else None


def choose_source(scope: Scope, plan: MonitoringPlan, forecast: Forecast | None) -> tuple[str, float, float]:
    cloud = float(forecast.metadata.get("cloudCover", 0.2)) if forecast else 0.2
    sources = plan.sources or ["sentinel-2"]
    if cloud > 0.3 and "sentinel-1" in sources:
        return "sentinel-1", SOURCE_RESOLUTION["sentinel-1"], SOURCE_COST["sentinel-1"]
    if scope.priority <= 1 and "planet" in sources:
        return "planet", SOURCE_RESOLUTION["planet"], SOURCE_COST["planet"]
    source = "sentinel-2" if "sentinel-2" in sources else sources[0]
    return source, SOURCE_RESOLUTION.get(source, 10.0), SOURCE_COST.get(source, 0.0)


def priority_for(scope: Scope, forecast: Forecast | None) -> int:
    score = scope.priority
    if forecast and forecast.probability >= 0.6:
        score = max(1, score - 1)
    if scope.subscription_tier == "24-7":
        score = max(1, score - 1)
    return int(min(5, max(1, score)))


def _month_key(moment: datetime) -> str:
    return moment.strftime("%Y-%m")


def spent_this_month(store: ProactiveStore, tenant: str, moment: datetime | None = None) -> float:
    moment = moment or utcnow()
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return store.total_cost(tenant, since=start.isoformat(timespec="seconds"))


def plan_acquisition(
    store: ProactiveStore,
    scope: Scope,
    plan: MonitoringPlan,
    *,
    forecast: Forecast | None = None,
    now: datetime | None = None,
    force: bool = False,
    actor: str = "scheduler",
) -> Acquisition | None:
    moment = now or utcnow()
    if plan.paused or plan.kill_switch or scope.status != "active":
        return None
    if spent_this_month(store, scope.tenant, moment) >= plan.budget_eur_per_month:
        store.audit(scope.tenant, "budget.cap-reached", actor=actor, detail={"scope": scope.id, "budget": plan.budget_eur_per_month})
        return None

    source, resolution, cost = choose_source(scope, plan, forecast)
    bucket = moment.strftime("%Y%m%d%H") if plan.cadence in {"6h", "12h", "daily"} else moment.strftime("%Y%m%d")
    key = f"{scope.id}:{bucket}:{source}"
    existing = store.find_acquisition_by_key(key)
    if existing and not force:
        return existing
    if not force:
        for prior in store.list_acquisitions(scope.id, 20):
            if prior.source != source or prior.status in {"rejected"}:
                continue
            prior_at = parse_iso(prior.scheduled_for)
            if prior_at and abs((moment - prior_at).total_seconds()) < cadence_hours(plan.cadence) * 3600 * 0.5:
                return prior
    if force:
        key = f"{key}:manual:{new_id('k')}"

    acquisition = Acquisition(
        id=new_id("acq"),
        scope_id=scope.id,
        source=source,
        scheduled_for=now_iso(moment),
        status="planned" if cost > 0 else "ordered",
        cloud_forecast=float(forecast.metadata.get("cloudCover", 0.2)) if forecast else 0.2,
        cost_eur=cost,
        priority=priority_for(scope, forecast),
        idempotency_key=key,
        bbox=scope.bbox,
        resolution_m=resolution,
        provenance={
            "actor": actor,
            "forecast": forecast.id if forecast else None,
            "plan": plan.cadence,
            "dryRun": source.startswith("sentinel"),
        },
    )
    store.save_acquisition(acquisition)
    store.add_cost(
        CostEntry(id=new_id("cost"), tenant=scope.tenant, scope_id=scope.id, kind="imagery", amount_eur=cost)
    )
    store.audit(
        scope.tenant,
        "acquisition.planned",
        actor=actor,
        detail={"scope": scope.id, "acquisition": acquisition.id, "source": source, "cost": cost, "priority": acquisition.priority},
    )
    if cost > 0:
        store.audit(scope.tenant, "acquisition.approval-required", actor=actor, detail={"acquisition": acquisition.id, "cost": cost, "source": source})
    return acquisition


def approve_acquisition(store: ProactiveStore, acquisition_id: str, *, actor: str = "ops") -> Acquisition:
    acquisition = next((a for a in store.list_acquisitions(limit=2000) if a.id == acquisition_id), None)
    if acquisition is None:
        raise KeyError(acquisition_id)
    if acquisition.status != "planned":
        return acquisition
    acquisition.status = "ordered"
    store.save_acquisition(acquisition)
    scope = store.get_scope(acquisition.scope_id)
    store.audit(scope.tenant if scope else "unknown", "acquisition.approved", actor=actor, detail={"acquisition": acquisition.id})
    return acquisition


def received_recently(store: ProactiveStore, scope: Scope, plan: MonitoringPlan, now: datetime | None = None) -> bool:
    last = store.last_received(scope.id)
    if last is None:
        return False
    return hours_since(last.received_at or last.scheduled_for, now) < cadence_hours(plan.cadence)


def tick(
    store: ProactiveStore,
    *,
    tenant: str | None = None,
    forecasts: list[Forecast] | None = None,
    now: datetime | None = None,
) -> dict:
    moment = now or utcnow()
    forecasts = forecasts or []
    planned: list[dict] = []
    retried: list[dict] = []
    for scope in store.list_scopes(tenant=tenant, status="active"):
        plan = store.get_plan(scope.id) or MonitoringPlan(scope_id=scope.id, cadence=scope.cadence)
        if received_recently(store, scope, plan, moment):
            continue
        acquisition = plan_acquisition(store, scope, plan, forecast=forecast_for_scope(scope, forecasts), now=moment)
        if acquisition:
            planned.append({"scope": scope.id, "acquisition": acquisition.id, "source": acquisition.source})
        for failed in [a for a in store.list_acquisitions(scope.id, 50) if a.status == "failed"]:
            if retry(store, failed.id, now=moment):
                retried.append({"scope": scope.id, "acquisition": failed.id})
    return {"planned": planned, "retried": retried, "at": now_iso(moment)}


def retry(store: ProactiveStore, acquisition_id: str, *, now: datetime | None = None) -> Acquisition | None:
    acquisition = next((a for a in store.list_acquisitions(limit=1000) if a.id == acquisition_id), None)
    if acquisition is None or acquisition.status not in {"failed", "planned", "ordered"}:
        return None
    moment = now or utcnow()
    acquisition.attempts += 1
    if acquisition.attempts >= MAX_ATTEMPTS:
        acquisition.status = "failed"
        acquisition.blind_spot_reason = "max retries reached"
        store.save_acquisition(acquisition)
        scope = store.get_scope(acquisition.scope_id)
        store.audit(scope.tenant if scope else "unknown", "acquisition.dead-letter", actor="scheduler", detail={"acquisition": acquisition.id})
        return acquisition
    acquisition.status = "ordered"
    acquisition.next_attempt_at = add_hours(moment, 2**acquisition.attempts)
    store.save_acquisition(acquisition)
    scope = store.get_scope(acquisition.scope_id)
    store.audit(scope.tenant if scope else "unknown", "acquisition.retry", actor="scheduler", detail={"acquisition": acquisition.id, "attempt": acquisition.attempts})
    return acquisition


def receive(
    store: ProactiveStore,
    acquisition_id: str,
    *,
    scene_id: str,
    cloud: float = 0.1,
    readiness: float | None = None,
) -> Acquisition:
    acquisition = next((a for a in store.list_acquisitions(limit=1000) if a.id == acquisition_id), None)
    if acquisition is None:
        raise KeyError(acquisition_id)
    acquisition.status = "received"
    acquisition.scene_id = scene_id
    acquisition.received_at = now_iso()
    acquisition.cloud_forecast = cloud
    acquisition.readiness = readiness if readiness is not None else round(max(0.0, 1.0 - cloud), 3)
    store.save_acquisition(acquisition)
    scope = store.get_scope(acquisition.scope_id)
    store.audit(scope.tenant if scope else "unknown", "acquisition.received", actor="pipeline", detail={"acquisition": acquisition.id, "scene": scene_id})
    return acquisition


def watch_now(store: ProactiveStore, scope_id: str, *, actor: str = "analyst", now: datetime | None = None) -> Acquisition | None:
    scope = store.get_scope(scope_id)
    if scope is None:
        raise KeyError(scope_id)
    plan = store.get_plan(scope_id) or MonitoringPlan(scope_id=scope_id, cadence=scope.cadence)
    return plan_acquisition(store, scope, plan, now=now, force=True, actor=actor)


def readiness(store: ProactiveStore, scope: Scope, plan: MonitoringPlan, now: datetime | None = None) -> dict:
    moment = now or utcnow()
    last = store.last_received(scope.id)
    age = hours_since(last.received_at if last else None, moment)
    cadence = cadence_hours(plan.cadence)
    freshness = max(0.0, min(1.0, 1 - age / max(cadence * 2, 1)))
    cloud = last.cloud_forecast if last else 1.0
    resolution = last.resolution_m if last else 999
    resolution_score = max(0.0, min(1.0, 10 / max(resolution, 0.1)))
    coverage = 1.0 if last else 0.0
    score = round(0.4 * freshness + 0.25 * (1 - cloud) + 0.2 * resolution_score + 0.15 * coverage, 3)
    return {
        "scopeId": scope.id,
        "score": score,
        "freshnessHours": round(age, 1) if age < 10**8 else None,
        "cloud": cloud,
        "resolutionM": resolution,
        "coverage": coverage,
        "status": "ok" if score >= 0.7 else "degraded" if score >= 0.4 else "blind",
        "sloBreached": age > scope.freshness_slo_hours if age < 10**8 else True,
    }


def calendar(store: ProactiveStore, scope_id: str, *, days: int = 14) -> list[dict]:
    cutoff = (utcnow() + timedelta(days=days)).isoformat(timespec="seconds")
    rows = [a for a in store.list_acquisitions(scope_id, 200) if a.scheduled_for <= cutoff]
    return [
        {
            "id": a.id,
            "scheduledFor": a.scheduled_for,
            "status": a.status,
            "source": a.source,
            "cloudForecast": a.cloud_forecast,
            "readiness": a.readiness,
            "costEur": a.cost_eur,
            "blindSpotReason": a.blind_spot_reason,
        }
        for a in sorted(rows, key=lambda item: item.scheduled_for)
    ]


def blind_spots(store: ProactiveStore, tenant: str, now: datetime | None = None) -> list[dict]:
    moment = now or utcnow()
    output = []
    for scope in store.list_scopes(tenant):
        plan = store.get_plan(scope.id) or MonitoringPlan(scope_id=scope.id, cadence=scope.cadence)
        state = readiness(store, scope, plan, moment)
        if state["status"] != "ok":
            output.append(
                {
                    "scopeId": scope.id,
                    "name": scope.name,
                    "region": scope.region,
                    "status": state["status"],
                    "freshnessHours": state["freshnessHours"],
                    "sloBreached": state["sloBreached"],
                    "mode": plan.coverage_mode,
                    "reason": "no recent acquisition" if state["freshnessHours"] is None else "freshness or cloud outside contract",
                }
            )
    return output


def coverage(store: ProactiveStore, tenant: str, now: datetime | None = None) -> list[dict]:
    moment = now or utcnow()
    rows = []
    for scope in store.list_scopes(tenant):
        plan = store.get_plan(scope.id) or MonitoringPlan(scope_id=scope.id, cadence=scope.cadence)
        state = readiness(store, scope, plan, moment)
        last = store.last_received(scope.id)
        rows.append(
            {
                "scopeId": scope.id,
                "name": scope.name,
                "kind": scope.kind,
                "region": scope.region,
                "bbox": scope.bbox,
                "center": scope.center,
                "areaKm2": round(scope.area_km2, 1),
                "cadence": plan.cadence,
                "status": scope.status,
                "lastAcquisition": last.received_at if last else None,
                "nextExpected": add_hours(moment, cadence_hours(plan.cadence)) if scope.status == "active" else None,
                "freshnessHours": state["freshnessHours"],
                "readiness": state["score"],
                "coverageStatus": state["status"],
                "blindSpot": state["status"] != "ok",
                "mode": plan.coverage_mode,
                "source": last.source if last else None,
            }
        )
    return rows


def import_airgap(store: ProactiveStore, scope_id: str, folder: str | Path, *, source: str = "drone") -> list[Acquisition]:
    folder = Path(folder)
    if not folder.exists():
        return []
    received = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".tif", ".tiff", ".png", ".jpg", ".jpeg"}:
            continue
        key = f"{scope_id}:airgap:{path.name}"
        if store.find_acquisition_by_key(key):
            continue
        acquisition = Acquisition(
            id=new_id("acq"),
            scope_id=scope_id,
            source=source,
            scheduled_for=now_iso(),
            status="received",
            cost_eur=0.0,
            idempotency_key=key,
            resolution_m=SOURCE_RESOLUTION.get(source, 10.0),
            scene_id=path.stem,
            received_at=now_iso(),
            readiness=1.0,
            provenance={"airgap": True, "file": str(path)},
        )
        store.save_acquisition(acquisition)
        received.append(acquisition)
    return received


def cost_report(store: ProactiveStore, tenant: str, *, days: int = 30, scope_id: str | None = None) -> dict:
    since = (utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
    entries = store.costs(tenant, since=since, scope_id=scope_id)
    by_kind: dict[str, float] = {}
    by_scope: dict[str, float] = {}
    for entry in entries:
        by_kind[entry.kind] = round(by_kind.get(entry.kind, 0) + entry.amount_eur, 2)
        by_scope[entry.scope_id] = round(by_scope.get(entry.scope_id, 0) + entry.amount_eur, 2)
    daily: dict[str, float] = {}
    for entry in entries:
        day = entry.at[:10]
        daily[day] = round(daily.get(day, 0) + entry.amount_eur, 2)
    values = list(daily.values())
    mean = sum(values) / max(1, len(values))
    anomaly = any(value > max(50.0, mean * 4) for value in values) if len(values) > 2 else False
    return {
        "tenant": tenant,
        "days": days,
        "totalEur": round(sum(e.amount_eur for e in entries), 2),
        "byKind": by_kind,
        "byScope": by_scope,
        "entries": len(entries),
        "daily": daily,
        "anomaly": anomaly,
        "budgetGuardrail": "per-scope monthly cap + tenant quota",
    }


def freshness_slo(store: ProactiveStore, tenant: str, now: datetime | None = None) -> dict:
    rows = coverage(store, tenant, now)
    breached = [row for row in rows if row["freshnessHours"] is None or row["freshnessHours"] > (
        store.get_scope(row["scopeId"]).freshness_slo_hours if store.get_scope(row["scopeId"]) else 168
    )]
    return {
        "scopes": len(rows),
        "breached": len(breached),
        "breaches": [{"scopeId": row["scopeId"], "freshnessHours": row["freshnessHours"]} for row in breached],
        "status": "ok" if not breached else "degraded",
    }


def plan_batch(store: ProactiveStore, tenant: str, *, limit: int = 10) -> list[Acquisition]:
    """Priority queue view for a worker: lowest priority number first, oldest first."""
    scope_tenants = {scope.id: scope.tenant for scope in store.list_scopes(tenant)}
    candidates = [
        a
        for a in store.list_acquisitions(limit=500)
        if a.status in {"planned", "ordered"} and scope_tenants.get(a.scope_id) == tenant
    ]
    candidates.sort(key=lambda a: (a.priority, a.scheduled_for))
    return candidates[:limit]


def round_trip(store: ProactiveStore, acquisition_id: str, *, cloud: float = 0.08) -> Acquisition:
    """Simulate the pipeline receiving and processing the scene, for demos/tests."""
    acq = receive(store, acquisition_id, scene_id=f"SCENE-{acquisition_id[-6:]}", cloud=cloud)
    scope = store.get_scope(acq.scope_id)
    store.add_cost(CostEntry(id=new_id("cost"), tenant=scope.tenant if scope else "unknown", scope_id=acq.scope_id, kind="inference", amount_eur=0.4))
    return acq
