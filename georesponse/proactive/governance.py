"""Governance: model registry, explainability, validation gates, keys and safety."""

from __future__ import annotations

import base64
import hashlib
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from cryptography.fernet import Fernet

from .models import (
    NON_GOALS,
    Alert,
    ModelEntry,
    MonitoringPlan,
    Scope,
    ValidationRecord,
    clamp,
    new_id,
    now_iso,
    parse_iso,
    utcnow,
)
from .baseline import calibration
from .store import ProactiveStore


class NonGoalError(PermissionError):
    pass


def enforce_non_goal(action: str) -> None:
    if action in NON_GOALS:
        raise NonGoalError(f"non-goal blocked: {action}")


class ModelRegistry:
    def __init__(self, store: ProactiveStore) -> None:
        self.store = store

    def register(self, name: str, version: str, *, metrics: dict[str, float] | None = None, status: str = "shadow", notes: str = "") -> ModelEntry:
        previous = self.store.get_model(name)
        entry = ModelEntry(
            name=name,
            version=version,
            status=status,
            metrics=metrics or {},
            rollback_to=previous.version if previous else None,
            notes=notes,
        )
        self.store.save_model(entry)
        self.store.audit("demo", "model.registered", actor="mlops", detail={"name": name, "version": version, "status": status})
        return entry

    def deploy(self, name: str, version: str, *, metrics: dict[str, float] | None = None) -> ModelEntry:
        current = self.store.get_model(name)
        entry = ModelEntry(
            name=name,
            version=version,
            status="deployed",
            metrics=metrics or (current.metrics if current else {}),
            rollback_to=current.version if current else None,
            notes="Promoted after validation.",
        )
        self.store.save_model(entry)
        self.store.audit("demo", "model.deployed", actor="mlops", detail={"name": name, "version": version, "rollbackTo": entry.rollback_to})
        return entry

    def rollback(self, name: str) -> ModelEntry:
        current = self.store.get_model(name)
        if not current or not current.rollback_to:
            raise ValueError(f"no rollback target for {name}")
        entry = ModelEntry(
            name=name,
            version=current.rollback_to,
            status="deployed",
            metrics=current.metrics,
            rollback_to=current.version,
            notes=f"Rolled back from {current.version}.",
        )
        self.store.save_model(entry)
        self.store.audit("demo", "model.rollback", actor="mlops", detail={"name": name, "version": entry.version})
        return entry

    def deployed(self, name: str) -> ModelEntry | None:
        entry = self.store.get_model(name)
        return entry if entry and entry.status == "deployed" else None


def explain_alert(alert: Alert) -> dict:
    why = alert.why or {}
    return {
        "alertId": alert.id,
        "modelVersion": alert.model_version,
        "confidence": alert.confidence,
        "severity": alert.severity,
        "factors": [
            {"factor": "change vs baseline", "value": f"{round(alert.observed*100, 1)}% vs {round(alert.baseline*100, 1)}%", "weight": 0.34},
            {"factor": "model confidence", "value": f"{round(alert.confidence*100)}%", "weight": 0.24},
            {"factor": "value at risk", "value": f"{alert.value_eur:,} EUR", "weight": 0.18},
            {"factor": "access", "value": alert.access, "weight": 0.12},
        ],
        "threshold": why.get("threshold"),
        "trend": why.get("trend"),
        "confirmation": why.get("confirmation"),
        "fusion": why.get("fusion"),
        "suppression": why.get("suppression"),
        "evidence": alert.evidence,
        "provenance": alert.provenance,
        "statement": "This alert is decision support. An analyst validates the evidence before any action.",
    }


def calibration_by(store: ProactiveStore, tenant: str, dimension: str = "change_type") -> list[dict]:
    alerts = [a for a in store.list_alerts(tenant) if a.status in {"resolved", "dismissed"}]
    buckets: dict[str, list[Alert]] = {}
    for alert in alerts:
        buckets.setdefault(str(getattr(alert, dimension, "unknown") or "unknown"), []).append(alert)
    rows = []
    for key, members in buckets.items():
        confidences = [a.confidence for a in members]
        outcomes = [a.status == "resolved" for a in members]
        rows.append({dimension: key, "calibration": calibration(confidences, outcomes), "n": len(members)})
    return rows


def false_alarm_cost(alerts: Iterable[Alert], *, analyst_hourly_eur: float = 78, minutes_per_alert: float = 25) -> dict:
    rows = list(alerts)
    dismissed = [a for a in rows if a.status == "dismissed"]
    hours = len(dismissed) * minutes_per_alert / 60
    return {
        "alerts": len(rows),
        "dismissed": len(dismissed),
        "analystHours": round(hours, 2),
        "costEur": round(hours * analyst_hourly_eur, 2),
        "byReason": {reason: sum(1 for a in dismissed if a.dismissed_reason == reason) for reason in {a.dismissed_reason for a in dismissed if a.dismissed_reason}},
    }


def override_analysis(store: ProactiveStore, tenant: str) -> dict:
    alerts = store.list_alerts(tenant)
    resolved = [a for a in alerts if a.status in {"resolved", "dismissed"}]
    rejected = [a for a in resolved if a.status == "dismissed"]
    approved = [a for a in resolved if a.status == "resolved"]
    return {
        "resolved": len(resolved),
        "approved": len(approved),
        "rejected": len(rejected),
        "overrideRate": round(len(rejected) / max(1, len(resolved)), 3),
        "reasons": {reason: sum(1 for a in rejected if a.dismissed_reason == reason) for reason in {a.dismissed_reason for a in rejected if a.dismissed_reason}},
    }


def precision_by(store: ProactiveStore, tenant: str, dimension: str = "change_type") -> list[dict]:
    alerts = [a for a in store.list_alerts(tenant) if a.status in {"resolved", "dismissed"}]
    buckets: dict[str, list[Alert]] = {}
    for alert in alerts:
        key = str(getattr(alert, dimension, "unknown") or "unknown")
        buckets.setdefault(key, []).append(alert)
    rows = []
    for key, members in buckets.items():
        confirmed = sum(1 for a in members if a.status == "resolved")
        rows.append(
            {
                dimension: key,
                "alerts": len(members),
                "confirmed": confirmed,
                "precision": round(confirmed / max(1, len(members)), 3),
            }
        )
    return sorted(rows, key=lambda row: -row["alerts"])


def privacy_review_proactive() -> dict:
    items = [
        ("scope_definition", "Every monitored scope has a named customer, purpose and exclusion zones."),
        ("lawful_basis", "Continuous acquisition has a documented lawful basis and DPA."),
        ("minimisation", "Resolution and cadence are the minimum needed for the decision."),
        ("retention", "Retention clock per alert and per scope; raw imagery deleted on schedule."),
        ("access", "Per-tenant roles: analyst, reviewer, auditor, customer viewer."),
        ("subprocessors", "Imagery provider, cloud, NPU vendor listed as subprocessors."),
        ("sovereignty", "On-site or sovereign deployment; no outbound network after delivery."),
        ("transparency", "Customer notice explains AI monitoring and human decisions."),
        ("human_review", "No automatic claim approval or crew dispatch."),
        ("incident", "Breach playbook, 72-hour notification, audit export."),
        ("surveillance", "No monitoring of people, protests, private life or protected groups."),
        ("scope_creep", "Quarterly scope review; a new scope requires a new purpose."),
    ]
    return {
        "policy": "Privacy review for persistent aerial monitoring",
        "items": [{"id": key, "requirement": text, "status": "engineered" if key in {"scope_definition", "minimisation", "sovereignty", "human_review", "surveillance"} else "pilot-gate"} for key, text in items],
        "note": "Engineering checklist, not legal advice.",
    }


class TenantKeyring:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant: str) -> Path:
        digest = hashlib.sha256(tenant.encode("utf-8")).hexdigest()[:24]
        return self.root / f"{digest}.key"

    def key(self, tenant: str) -> bytes:
        path = self._path(tenant)
        if path.exists():
            return path.read_bytes()
        key = Fernet.generate_key()
        path.write_bytes(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return key

    def encrypt(self, tenant: str, payload: str) -> tuple[str, str]:
        token = Fernet(self.key(tenant)).encrypt(payload.encode("utf-8")).decode("ascii")
        return token, hashlib.sha256(self.key(tenant)).hexdigest()[:12]

    def decrypt(self, tenant: str, token: str) -> str:
        return Fernet(self.key(tenant)).decrypt(token.encode("ascii")).decode("utf-8")


class KillSwitch:
    def __init__(self, store: ProactiveStore) -> None:
        self.store = store

    def set(self, tenant: str, active: bool, *, actor: str = "ops") -> dict:
        self.store.meta_set(f"kill:{tenant}", "1" if active else "0")
        self.store.audit(tenant, "kill-switch.set", actor=actor, detail={"active": active})
        return {"tenant": tenant, "active": active}

    def active(self, tenant: str) -> bool:
        return self.store.meta_get(f"kill:{tenant}", "0") == "1"


class RateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self.events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            timestamps = [t for t in self.events.get(key, []) if now - t < self.window]
            if len(timestamps) >= self.limit:
                self.events[key] = timestamps
                return False
            timestamps.append(now)
            self.events[key] = timestamps
            return True


class OnCallSchedule:
    def __init__(self, analysts: list[str] | None = None) -> None:
        self.analysts = analysts or ["A. Weber", "M. Keller", "S. Okafor"]

    def current(self, moment: datetime | None = None) -> dict:
        moment = moment or utcnow()
        index = (moment.toordinal() + moment.hour // 8) % len(self.analysts)
        return {"primary": self.analysts[index], "secondary": self.analysts[(index + 1) % len(self.analysts)], "window": "8h"}

    def escalate(self, minutes_open: int) -> dict:
        if minutes_open >= 60:
            return {"level": 2, "to": "team-lead", "action": "page"}
        if minutes_open >= 30:
            return {"level": 1, "to": "secondary", "action": "notify"}
        return {"level": 0, "to": "primary", "action": "wait"}


class ValidationGate:
    """First N alerts per scope are analyst-validated before customer notification."""

    def __init__(self, store: ProactiveStore) -> None:
        self.store = store

    def can_notify(self, scope_id: str, plan: MonitoringPlan, alert: Alert) -> tuple[bool, str]:
        if alert.validated_by:
            return True, "analyst validated"
        count = self.store.validation_count(scope_id)
        if count >= plan.first_n_alerts_require_analyst:
            return True, "scope validation gate passed"
        return False, f"shadow validation {count}/{plan.first_n_alerts_require_analyst}"

    def record(self, scope_id: str, alert_id: str, analyst: str, decision: str, note: str = "") -> ValidationRecord:
        record = ValidationRecord(scope_id=scope_id, analyst=analyst, alert_id=alert_id, decision=decision, note=note)
        self.store.add_validation(record)
        self.store.audit("demo", "validation.recorded", alert_id=alert_id, actor=analyst, detail={"scope": scope_id, "decision": decision})
        return record


def retention_policy(store: ProactiveStore, tenant: str, days: int = 365, now: datetime | None = None) -> dict:
    return store.purge(tenant, days, now)


def alert_quality(store: ProactiveStore, tenant: str) -> dict:
    alerts = store.list_alerts(tenant)
    closed = [a for a in alerts if a.status in {"resolved", "dismissed"}]
    confirmed = [a for a in closed if a.status == "resolved"]
    resolved_without_assignee = [a for a in alerts if a.status == "resolved" and not a.assignee]
    return {
        "alerts": len(alerts),
        "closed": len(closed),
        "precision": round(len(confirmed) / max(1, len(closed)), 3),
        "resolvedWithoutAssignee": len(resolved_without_assignee),
        "rejectedReasons": false_alarm_cost(alerts)["byReason"],
        "falseAlarm": false_alarm_cost(alerts),
    }


def governance_snapshot(store: ProactiveStore, tenant: str) -> dict:
    return {
        "models": [m.to_dict() for m in store.list_models()],
        "audit": {"ok": store.verify_audit(tenant)[0], "message": store.verify_audit(tenant)[1]},
        "killSwitch": KillSwitch(store).active(tenant),
        "quality": alert_quality(store, tenant),
        "overrides": override_analysis(store, tenant),
        "privacy": privacy_review_proactive(),
        "nonGoals": list(NON_GOALS),
        "retention": {"defaultDays": 365, "policy": "raw imagery deleted after claim decision + legal minimum"},
    }


def incident_review_template(alert: Alert) -> dict:
    return {
        "incidentId": alert.incident_id,
        "questions": [
            "Was the alert actionable?",
            "What did the analyst do?",
            "Was the evidence sufficient?",
            "Was the SLA met?",
            "What should the model learn?",
        ],
        "reviewers": ["analyst", "team lead"],
        "dueHours": 48,
        "humanAuthored": True,
    }
