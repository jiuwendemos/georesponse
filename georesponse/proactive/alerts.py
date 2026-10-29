"""Alert schema, incident grouping, lifecycle, routing and handoff.

The alert is the unit of human work.  It carries the evidence and the “why”,
lives through explicit states, and can always be traced back to an audit event.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import (
    ALERT_SCHEMA_VERSION,
    ALERT_STATES,
    DISMISS_REASONS,
    Alert,
    Incident,
    MonitoringPlan,
    Scope,
    add_hours,
    clamp,
    hours_since,
    new_id,
    now_iso,
    parse_iso,
    utcnow,
)
from .store import ProactiveStore

VALID_TRANSITIONS = {
    "new": {"acknowledged", "assigned", "dismissed"},
    "acknowledged": {"assigned", "investigating", "dismissed", "resolved"},
    "assigned": {"investigating", "acknowledged", "dismissed", "resolved"},
    "investigating": {"resolved", "dismissed", "assigned"},
    "resolved": set(),
    "dismissed": set(),
}

SEVERITY_WEIGHT = {"red": 1.0, "orange": 0.65, "yellow": 0.35}
ACCESS_WEIGHT = {"blocked": 1.0, "flooded": 0.9, "restricted": 0.7, "debris": 0.8, "slow": 0.55, "clear": 0.2}


def validate_alert(payload: dict) -> dict:
    required = ["id", "tenant", "scope_id", "title", "severity", "change_type", "lon", "lat", "confidence"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"alert missing fields: {missing}")
    if payload["severity"] not in SEVERITY_WEIGHT:
        raise ValueError(f"bad severity: {payload['severity']}")
    if payload.get("schema_version", ALERT_SCHEMA_VERSION) != ALERT_SCHEMA_VERSION:
        raise ValueError("unsupported alert schema")
    return payload


def urgency_score(alert: Alert) -> float:
    value_score = clamp(math.log10(max(1, alert.value_eur)) / 8, 0, 1)
    population_score = clamp(math.log10(max(1, alert.population)) / 5, 0, 1)
    score = (
        0.34 * SEVERITY_WEIGHT.get(alert.severity, 0.4)
        + 0.24 * alert.confidence
        + 0.18 * value_score
        + 0.12 * population_score
        + 0.12 * ACCESS_WEIGHT.get(alert.access, 0.4)
    )
    alert.urgency = round(score, 3)
    return alert.urgency


def make_alert(
    *,
    tenant: str,
    scope: Scope,
    finding: dict,
    plan: MonitoringPlan,
    observation: dict,
    model_version: str,
    evidence: dict | None = None,
    incident_id: str | None = None,
) -> Alert:
    severity = "red" if finding["confidence"] >= 0.85 and finding["observed"] >= 0.12 else "orange" if finding["confidence"] >= 0.62 else "yellow"
    title = f"{observation.get('changeType', 'change').title()} change in {scope.name}"
    alert = Alert(
        id=new_id("ALT"),
        tenant=tenant,
        scope_id=scope.id,
        title=title,
        summary=observation.get("summary", f"{findings_phrase(finding)} in {scope.name}; analyst validation required."),
        severity=severity,
        urgency=0.0,
        confidence=float(finding["confidence"]),
        change_type=observation.get("changeType", "structure"),
        observed=float(finding["observed"]),
        baseline=float(finding["baseline"]["mean"]),
        lon=float(observation.get("lon", scope.center[0])),
        lat=float(observation.get("lat", scope.center[1])),
        incident_id=incident_id,
        sla_due=add_hours(utcnow(), plan.sla_hours),
        asset=observation.get("asset"),
        value_eur=int(observation.get("valueEur", scope.metadata.get("valueEur", 0))),
        population=int(observation.get("population", scope.metadata.get("population", 0))),
        access=observation.get("access", "clear"),
        source=observation.get("source", "sentinel-2"),
        model_version=model_version,
        evidence=evidence or {},
        why=why_panel(finding, scope, observation),
        provenance={
            "imagery": observation.get("imagery", "simulated demo pack"),
            "acquired": observation.get("acquired"),
            "model": model_version,
            "baseline": finding["baseline"],
            "fusion": finding["fusion"],
            "suppression": finding["suppression"],
        },
        validated_by=observation.get("validatedBy"),
        validation_count=int(observation.get("validationCount", 0)),
        tags=observation.get("tags", []),
    )
    urgency_score(alert)
    validate_alert(alert.to_dict())
    return alert


def findings_phrase(finding: dict) -> str:
    return f"{round(finding['observed'] * 100, 1)}% change against a {round(finding['baseline']['mean'] * 100, 1)}% baseline"


def dedupe_key(alert: Alert) -> str:
    return f"{alert.scope_id}:{alert.change_type}:{round(alert.lon, 2)}:{round(alert.lat, 2)}"


def find_duplicate(store: ProactiveStore, alert: Alert, *, window_hours: int = 6) -> Alert | None:
    cutoff = (utcnow() - timedelta(hours=window_hours)).isoformat(timespec="seconds")
    for existing in store.list_alerts(tenant=alert.tenant, scope_id=alert.scope_id, limit=200):
        if existing.created_at < cutoff:
            continue
        if existing.change_type != alert.change_type:
            continue
        if math.dist((existing.lon, existing.lat), (alert.lon, alert.lat)) * 111 < 2.0:
            return existing
    return None


def group_into_incident(store: ProactiveStore, alert: Alert, *, window_hours: int = 6) -> Incident:
    if alert.incident_id:
        incident = store.get_incident(alert.incident_id)
        if incident:
            if alert.id not in incident.alert_ids:
                incident.alert_ids.append(alert.id)
                incident.timeline.append({"at": now_iso(), "event": "alert.linked", "alertId": alert.id})
                store.save_incident(incident)
            return incident
    cutoff = (utcnow() - timedelta(hours=window_hours)).isoformat(timespec="seconds")
    for incident in store.list_incidents(tenant=alert.tenant, status="open"):
        if incident.scope_id != alert.scope_id or incident.opened_at < cutoff:
            continue
        incident.alert_ids.append(alert.id)
        incident.timeline.append({"at": now_iso(), "event": "alert.linked", "alertId": alert.id})
        incident.severity = max(incident.severity, alert.severity, key=lambda s: SEVERITY_WEIGHT.get(s, 0))
        store.save_incident(incident)
        alert.incident_id = incident.id
        return incident
    incident = Incident(
        id=new_id("INC"),
        tenant=alert.tenant,
        scope_id=alert.scope_id,
        title=f"{alert.change_type.title()} incident · {alert.scope_id}",
        severity=alert.severity,
        alert_ids=[alert.id],
        summary=alert.summary,
        timeline=[{"at": now_iso(), "event": "incident.opened", "alertId": alert.id}],
    )
    store.save_incident(incident)
    alert.incident_id = incident.id
    return incident


def route_alert(alert: Alert, rules: list[dict] | None = None, analysts: list[str] | None = None) -> dict:
    rules = rules or []
    for rule in rules:
        if rule.get("scopeId") and rule["scopeId"] != alert.scope_id:
            continue
        if rule.get("changeType") and rule["changeType"] != alert.change_type:
            continue
        if rule.get("minSeverity"):
            order = {"yellow": 0, "orange": 1, "red": 2}
            if order.get(alert.severity, 0) < order.get(rule["minSeverity"], 0):
                continue
        return {"team": rule.get("team", "watch"), "assignee": rule.get("assignee"), "via": "rule"}
    analysts = analysts or ["A. Weber", "M. Keller", "S. Okafor"]
    digest = hashlib.sha256(alert.dedupe_key.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(analysts)
    return {"team": "watch", "assignee": analysts[index], "via": "round-robin"}


def transition(
    store: ProactiveStore,
    alert_id: str,
    action: str,
    *,
    actor: str = "analyst",
    note: str = "",
    assignee: str | None = None,
    reason: str | None = None,
) -> Alert:
    alert = store.get_alert(alert_id)
    if alert is None:
        raise KeyError(alert_id)
    target = {
        "acknowledge": "acknowledged",
        "assign": "assigned",
        "investigate": "investigating",
        "resolve": "resolved",
        "dismiss": "dismissed",
    }.get(action, action)
    if target not in ALERT_STATES:
        raise ValueError(f"unknown action: {action}")
    if target not in VALID_TRANSITIONS.get(alert.status, set()):
        raise ValueError(f"invalid transition {alert.status} -> {target}")
    if target == "dismissed" and reason not in DISMISS_REASONS:
        raise ValueError(f"dismissal requires a reason from {sorted(DISMISS_REASONS)}")
    alert.status = target
    alert.updated_at = now_iso()
    if target == "acknowledged":
        alert.acknowledged_at = now_iso()
    if target == "assigned":
        alert.assignee = assignee or alert.assignee or actor
        alert.acknowledged_at = alert.acknowledged_at or now_iso()
    if target == "resolved":
        alert.resolved_at = now_iso()
    if target == "dismissed":
        alert.dismissed_reason = reason
        alert.dismissal_note = note
    store.save_alert(alert)
    if alert.incident_id:
        incident = store.get_incident(alert.incident_id)
        if incident:
            incident.timeline.append({"at": now_iso(), "event": f"alert.{target}", "alertId": alert.id, "actor": actor, "note": note})
            store.save_incident(incident)
    store.audit(alert.tenant, f"alert.{target}", alert_id=alert.id, actor=actor, detail={"note": note, "reason": reason, "assignee": alert.assignee})
    return alert


def bulk_action(store: ProactiveStore, alert_ids: Iterable[str], action: str, *, actor: str = "analyst", assignee: str | None = None, reason: str | None = None) -> dict:
    ids = list(alert_ids)
    if len(ids) > 50:
        raise ValueError("bulk actions are limited to 50 alerts")
    done, failed = [], []
    for alert_id in ids:
        try:
            transition(store, alert_id, action, actor=actor, assignee=assignee, reason=reason)
            done.append(alert_id)
        except Exception as exc:  # noqa: BLE001 - returned as a per-item result
            failed.append({"id": alert_id, "error": str(exc)})
    store.audit("demo", "alert.bulk-action", actor=actor, detail={"action": action, "done": len(done), "failed": len(failed)})
    return {"done": done, "failed": failed}


def sla_status(alert: Alert, now: datetime | None = None) -> dict:
    moment = now or utcnow()
    due = parse_iso(alert.sla_due)
    if not due or alert.status in {"resolved", "dismissed"}:
        return {"breached": False, "minutesRemaining": None, "due": alert.sla_due}
    remaining = (due - moment).total_seconds() / 60
    return {"breached": remaining < 0, "minutesRemaining": round(remaining), "due": alert.sla_due}


def sla_breaches(store: ProactiveStore, tenant: str, now: datetime | None = None) -> list[dict]:
    rows = []
    for alert in store.list_alerts(tenant):
        state = sla_status(alert, now)
        if state["breached"]:
            rows.append({"id": alert.id, "title": alert.title, "scopeId": alert.scope_id, "assignee": alert.assignee, **state})
    return rows


def incident_timeline(store: ProactiveStore, incident_id: str) -> list[dict]:
    incident = store.get_incident(incident_id)
    if not incident:
        raise KeyError(incident_id)
    return incident.timeline


def why_panel(finding: dict, scope: Scope, observation: dict) -> dict:
    return {
        "summary": findings_phrase(finding),
        "threshold": finding["baseline"],
        "trend": finding["trend"],
        "abruptness": finding["abruptness"],
        "confirmation": finding["temporalConfirmation"],
        "fusion": finding["fusion"],
        "suppression": finding["suppression"],
        "scope": {"name": scope.name, "kind": scope.kind, "assetClass": scope.asset_class},
        "evidence": {
            "before": observation.get("evidenceBefore"),
            "after": observation.get("evidenceAfter"),
            "observation": observation.get("observation"),
        },
        "human": "An analyst validates this alert before any customer action.",
    }


def handoff_payload(alert: Alert, target: str) -> dict:
    base = {
        "alertId": alert.id,
        "incidentId": alert.incident_id,
        "scopeId": alert.scope_id,
        "title": alert.title,
        "severity": alert.severity,
        "confidence": alert.confidence,
        "summary": alert.summary,
        "location": {"lon": alert.lon, "lat": alert.lat},
        "valueEur": alert.value_eur,
        "population": alert.population,
        "access": alert.access,
        "evidence": alert.evidence,
        "provenance": alert.provenance,
        "humanReviewRequired": True,
    }
    if target in {"assessment", "reactive"}:
        return {**base, "kind": "reactive-assessment", "note": "Open a reactive assessment with the same evidence."}
    if target in {"claim", "guidewire", "duckcreek"}:
        return {
            **base,
            "kind": "claim-draft",
            "system": target,
            "draftOnly": True,
            "requiresAdjuster": True,
        }
    if target in {"inspection", "maximo", "sap"}:
        return {**base, "kind": "inspection-request", "system": target, "draftOnly": True, "priority": 1 if alert.severity == "red" else 2}
    if target == "dispatch":
        return {**base, "kind": "field-dispatch", "draftOnly": True, "teams": 1, "note": "A human commits the team."}
    raise ValueError(f"unknown handoff target: {target}")


def fatigue_budget(store: ProactiveStore, tenant: str, *, analysts: int = 4, shift_hours: int = 8, now: datetime | None = None) -> dict:
    moment = now or utcnow()
    since = (moment - timedelta(hours=shift_hours)).isoformat(timespec="seconds")
    alerts = [a for a in store.list_alerts(tenant) if a.created_at >= since]
    per_analyst = round(len(alerts) / max(1, analysts), 2)
    budget = 8
    return {
        "periodHours": shift_hours,
        "alerts": len(alerts),
        "analysts": analysts,
        "perAnalyst": per_analyst,
        "budgetPerAnalyst": budget,
        "overBudget": per_analyst > budget,
        "advice": "Group or digest alerts" if per_analyst > budget else "within budget",
    }


def digest(store: ProactiveStore, tenant: str, *, hours: int = 24, now: datetime | None = None) -> dict:
    moment = now or utcnow()
    cutoff = (moment - timedelta(hours=hours)).isoformat(timespec="seconds")
    alerts = [a for a in store.list_alerts(tenant) if a.created_at >= cutoff]
    open_alerts = [a for a in alerts if a.status not in {"resolved", "dismissed"}]
    return {
        "tenant": tenant,
        "periodHours": hours,
        "generatedAt": now_iso(moment),
        "alerts": len(alerts),
        "open": len(open_alerts),
        "headline": f"{len(alerts)} alerts, {len(open_alerts)} open, {len([a for a in alerts if a.severity == 'red'])} high risk",
        "sections": {
            "new": [mobile_card(a) for a in alerts if a.status == "new"],
            "inProgress": [mobile_card(a) for a in alerts if a.status in {"acknowledged", "assigned", "investigating"}],
            "resolved": [mobile_card(a) for a in alerts if a.status == "resolved"],
            "noAction": [mobile_card(a) for a in alerts if a.status == "dismissed"],
        },
        "fatigue": fatigue_budget(store, tenant, now=moment),
    }


def mobile_card(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "title": alert.title,
        "severity": alert.severity,
        "confidence": alert.confidence,
        "scopeId": alert.scope_id,
        "status": alert.status,
        "assignee": alert.assignee,
        "location": {"lon": alert.lon, "lat": alert.lat},
        "slaDue": alert.sla_due,
        "incidentId": alert.incident_id,
        "deepLink": f"/#watch/alert/{alert.id}",
    }


def customer_status_update(alert: Alert, *, author: str, message: str) -> dict:
    return {
        "alertId": alert.id,
        "incidentId": alert.incident_id,
        "author": author,
        "message": message,
        "generated": False,
        "publishedAt": now_iso(),
        "note": "Human-authored only. No generated customer warning.",
        "visible": True,
    }


def dismissal_reasons() -> dict:
    return dict(DISMISS_REASONS)
