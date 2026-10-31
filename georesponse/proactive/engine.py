"""Proactive orchestration: observation in, reviewed alert out.

This is the seam the UI and API use.  It composes the scheduler, baseline, alert
lifecycle, notifications and governance into one deterministic cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import alerts as alert_ops
from . import anticipation
from .baseline import BaselineEngine, apply_feedback, drift_score
from .governance import (
    KillSwitch,
    ModelRegistry,
    OnCallSchedule,
    RateLimiter,
    ValidationGate,
    alert_quality,
    explain_alert,
    governance_snapshot,
)
from .models import Alert, CostEntry, Forecast, MonitoringPlan, now_iso, parse_iso, utcnow
from .notifications import NotificationService, preferences_payload
from .scheduler import blind_spots, coverage, cost_report, freshness_slo, tick as scheduler_tick
from .store import ProactiveStore
from ..laix_adapter import get_facade


class ProactiveEngine:
    def __init__(self, store: ProactiveStore, *, secret: str = "demo-webhook-secret", base_url: str = "https://georesponse.example/", live_channels: bool = False) -> None:
        self.store = store
        self.baselines = BaselineEngine(store)
        self.notifications = NotificationService(store, secret=secret, base_url=base_url, live=live_channels)
        self.registry = ModelRegistry(store)
        self.validation = ValidationGate(store)
        self.limiter = RateLimiter(limit=120, window_seconds=60)
        self.oncall = OnCallSchedule()
        self.decisions = get_facade(store)

    # ------------------------------------------------------------------ ingest
    def ingest(self, scope_id: str, observation: dict, *, model_version: str = "gr-changenet-1.4.2", now: datetime | None = None) -> dict:
        scope = self.store.get_scope(scope_id)
        if scope is None:
            raise KeyError(scope_id)
        plan = self.store.get_plan(scope_id) or MonitoringPlan(scope_id=scope_id, cadence=scope.cadence, recipients=scope.recipients)
        if plan.paused or plan.kill_switch or KillSwitch(self.store).active(scope.tenant) or scope.status != "active":
            self.store.audit(scope.tenant, "observation.suppressed", actor="pipeline", detail={"scope": scope_id, "reason": "paused or kill switch"})
            return {"status": "suppressed", "reason": "paused or kill switch"}
        finding = self.baselines.observe_and_store(scope, plan, {**observation, "modelVersion": model_version})
        if not finding["alert"]:
            return {"status": "no-alert", "finding": finding}
        alert = alert_ops.make_alert(
            tenant=scope.tenant,
            scope=scope,
            finding=finding,
            plan=plan,
            observation=observation,
            model_version=model_version,
            evidence={
                "before": observation.get("evidenceBefore"),
                "after": observation.get("evidenceAfter"),
                "observation": observation.get("observation"),
            },
        )
        duplicate = alert_ops.find_duplicate(self.store, alert)
        if duplicate:
            duplicate.updated_at = now_iso(now)
            duplicate.evidence = {**duplicate.evidence, "latest": alert.evidence}
            self.store.save_alert(duplicate)
            self.store.audit(scope.tenant, "alert.deduplicated", alert_id=duplicate.id, actor="pipeline", detail={"new": alert.id})
            return {"status": "duplicate", "alert": duplicate.to_dict(), "finding": finding}
        incident = alert_ops.group_into_incident(self.store, alert)
        route = alert_ops.route_alert(alert, rules=plan.escalation, analysts=[self.oncall.current(now)["primary"]])
        alert.assignee = route.get("assignee")
        triage: dict | None = None
        try:
            roster = [route.get("assignee")] if route.get("assignee") else None
            triage = self.decisions.triage(alert, plan=plan, analysts=roster)
            if self.decisions.mode == "laix":
                verb = triage["authoritative"]["verb"]
                if verb in {"wait", "ask", "guide"}:
                    # LAIX says this is not yet worth an owner.  Keep the alert
                    # in the inbox, but do not imply that someone is working it.
                    alert.assignee = None
                elif verb == "escalate":
                    alert.tags = list(dict.fromkeys([*alert.tags, "sla-escalated"]))
        except Exception as exc:  # noqa: BLE001 - LAIX must never break ingest
            self.store.audit(
                scope.tenant,
                "laix.error",
                alert_id=alert.id,
                actor="laix",
                detail={"error": f"{type(exc).__name__}: {exc}"},
            )
        self.store.save_alert(alert)
        self.store.add_cost(CostEntry(id=f"cost-{alert.id}", tenant=scope.tenant, scope_id=scope.id, kind="analyst", amount_eur=0.0))
        self.store.audit(scope.tenant, "alert.created", alert_id=alert.id, actor="pipeline", detail={"scope": scope.id, "incident": incident.id, "severity": alert.severity})
        allowed, gate_reason = self.validation.can_notify(scope.id, plan, alert)
        sent: list[dict] = []
        if allowed:
            queued = self.notifications.enqueue(alert, prefs=self.store.get_preferences(scope.tenant), moment=now)
            sent = [n.to_dict() for n in queued]
        else:
            self.store.audit(scope.tenant, "notification.shadow-gated", alert_id=alert.id, detail={"gate": gate_reason})
        return {
            "status": "alert",
            "alert": alert.to_dict(),
            "incident": incident.to_dict(),
            "finding": finding,
            "route": route,
            "notifications": sent,
            "gate": gate_reason,
            "decision": triage,
        }

    # --------------------------------------------------------------- lifecycle
    def review(
        self,
        alert_id: str,
        action: str,
        *,
        actor: str = "analyst",
        note: str = "",
        assignee: str | None = None,
        reason: str | None = None,
    ) -> dict:
        alert = self.store.get_alert(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        scope = self.store.get_scope(alert.scope_id)
        plan = self.store.get_plan(alert.scope_id) or (MonitoringPlan(scope_id=alert.scope_id, cadence=scope.cadence) if scope else None)
        updated = alert_ops.transition(self.store, alert_id, action, actor=actor, note=note, assignee=assignee, reason=reason)
        if scope and plan and action in {"acknowledge", "assign", "investigate"}:
            if updated.validation_count < plan.first_n_alerts_require_analyst:
                self.validation.record(scope.id, updated.id, actor, "validated", note)
                updated.validation_count += 1
                updated.validated_by = actor
                self.store.save_alert(updated)
        if scope and action in {"dismiss", "resolve"}:
            self.validation.record(scope.id, updated.id, actor, "rejected" if action == "dismiss" else "confirmed", note)
            apply_feedback(self.store, scope)
        return updated.to_dict()

    def incident_view(self, incident_id: str) -> dict:
        incident = self.store.get_incident(incident_id)
        if not incident:
            raise KeyError(incident_id)
        alerts = [a for a in self.store.list_alerts(incident.tenant) if a.id in incident.alert_ids]
        return {
            "incident": incident.to_dict(),
            "alerts": [a.to_dict() for a in alerts],
            "evidence": [a.evidence for a in alerts],
            "timeline": incident.timeline,
            "humanReviewRequired": True,
        }

    def scope_trend(self, scope_id: str) -> dict:
        baselines = self.store.list_baselines(scope_id)
        return {
            "scopeId": scope_id,
            "series": [
                {"metric": baseline.metric, "values": baseline.values, "trend": baseline.trend, "season": baseline.season, "mean": baseline.mean, "std": baseline.std}
                for baseline in baselines
            ],
        }

    def explain(self, alert_id: str) -> dict:
        alert = self.store.get_alert(alert_id)
        if not alert:
            raise KeyError(alert_id)
        return explain_alert(alert)

    def handoff(self, alert_id: str, target: str) -> dict:
        alert = self.store.get_alert(alert_id)
        if not alert:
            raise KeyError(alert_id)
        return alert_ops.handoff_payload(alert, target)

    # ------------------------------------------------------------------- tick
    def run_tick(self, *, tenant: str | None = None, now: datetime | None = None, forecasts: list[Forecast] | None = None) -> dict:
        moment = now or utcnow()
        scheduled = scheduler_tick(self.store, tenant=tenant, forecasts=forecasts or [], now=moment)
        deliveries = self.notifications.deliver_due(moment)
        breaches = alert_ops.sla_breaches(self.store, tenant or "demo", moment)
        quality = alert_quality(self.store, tenant or "demo")
        fatigue = alert_ops.fatigue_budget(self.store, tenant or "demo", now=moment)
        self.store.audit(tenant or "demo", "scheduler.tick", actor="scheduler", detail={"planned": len(scheduled["planned"]), "sent": len(deliveries["sent"]), "sla": len(breaches)})
        return {
            "at": now_iso(moment),
            "scheduled": scheduled,
            "deliveries": deliveries,
            "slaBreaches": breaches,
            "quality": quality,
            "fatigue": fatigue,
        }

    # ---------------------------------------------------------------- views
    def watch(self, tenant: str, forecasts: list[Forecast]) -> dict:
        return {
            "watchlist": anticipation.pre_event_watchlist(self.store, tenant, forecasts),
            "heatmap": anticipation.portfolio_heatmap(self.store, tenant, forecasts),
            "tasking": anticipation.watch_now_plan(self.store, tenant, forecasts),
            "coverage": coverage(self.store, tenant),
            "blindSpots": blind_spots(self.store, tenant),
            "freshness": freshness_slo(self.store, tenant),
        }

    def dashboard(self, tenant: str) -> dict:
        alerts = self.store.list_alerts(tenant)
        closed = [a for a in alerts if a.status in {"resolved", "dismissed"}]
        confirmed = [a for a in closed if a.status == "resolved"]
        scopes = self.store.list_scopes(tenant)
        total_area = sum(scope.area_km2 for scope in scopes) or 1
        total_cost = self.store.total_cost(tenant)
        breaches = alert_ops.sla_breaches(self.store, tenant)
        latest_notifications = self.store.list_notifications(tenant=tenant, limit=10)
        return {
            "tenant": tenant,
            "alerts": len(alerts),
            "open": len([a for a in alerts if a.status not in {"resolved", "dismissed"}]),
            "highRisk": len([a for a in alerts if a.severity == "red" and a.status not in {"resolved", "dismissed"}]),
            "precision": round(len(confirmed) / max(1, len(closed)), 3),
            "actionConversion": round(len(confirmed) / max(1, len(closed)), 3),
            "slaBreaches": len(breaches),
            "scopes": len(scopes),
            "activeScopes": len([s for s in scopes if s.status == "active"]),
            "monitoredKm2": round(total_area, 1),
            "costPerKm2": round(total_cost / total_area, 2),
            "fatigue": alert_ops.fatigue_budget(self.store, tenant),
            "freshness": freshness_slo(self.store, tenant),
            "blindSpots": blind_spots(self.store, tenant),
            "onCall": self.oncall.current(),
            "notifications": [
                {"id": n.id, "alertId": n.alert_id, "channel": n.channel, "status": n.status, "attempts": n.attempts}
                for n in latest_notifications
            ],
            "models": [m.to_dict() for m in self.store.list_models()],
            "governance": governance_snapshot(self.store, tenant),
        }

    def pilot_report(self, tenant: str) -> dict:
        dashboard = self.dashboard(tenant)
        alerts = self.store.list_alerts(tenant)
        lead_times = [float(a.why.get("leadTimeHours", 0) or 0) for a in alerts if a.why.get("leadTimeHours")]
        gates = {
            "precision": dashboard["precision"] >= 0.80,
            "fatigue": not dashboard["fatigue"]["overBudget"],
            "sla": dashboard["slaBreaches"] == 0,
            "shadowComplete": self.store.validation_count("scope-ahr-corridor") >= 3,
        }
        return {
            "tenant": tenant,
            "dashboard": dashboard,
            "leadTimeHours": round(sum(lead_times) / max(1, len(lead_times)), 1) if lead_times else None,
            "gates": gates,
            "launchReady": all(gates.values()),
            "criteria": {"precision": 0.80, "fatiguePerAnalyst": 8, "slaBreaches": 0, "shadowValidations": 3},
            "generatedAt": now_iso(),
        }

    def prefs(self, tenant: str) -> dict:
        return preferences_payload(self.store.get_preferences(tenant))
