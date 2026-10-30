"""PostgreSQL-backed proactive store.

A compact JSONB implementation of the same interface as the SQLite store, so the
API and engine can run against PostgreSQL without a code fork.  The dedicated
schema in `deploy/sql/postgres_schema.sql` is the long-term reporting schema; this
table is the operational store used by the app.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from ..audit import GENESIS, hash_event
from ..proactive.models import (
    Acquisition,
    Alert,
    Baseline,
    CostEntry,
    Forecast,
    Incident,
    ModelEntry,
    MonitoringPlan,
    Notification,
    Scope,
    TenantPreferences,
    ValidationRecord,
    new_id,
    now_iso,
)
from ..proactive.store import ProactiveStore


class PostgresUnavailable(RuntimeError):
    pass


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise PostgresUnavailable("GEORESPONSE_POSTGRES_DSN is not set")
        import psycopg
        from psycopg.types.json import Json

        self._json = Json
        self.conn = psycopg.connect(dsn, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS gr_records ("
                "kind TEXT NOT NULL, id TEXT NOT NULL, tenant TEXT, status TEXT, updated_at TIMESTAMPTZ DEFAULT now(), "
                "data JSONB NOT NULL, PRIMARY KEY(kind,id))"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS gr_records_lookup ON gr_records(kind,tenant,status)")

    # ----------------------------------------------------------------- helpers
    def _put(self, kind: str, record_id: str, tenant: str | None, status: str | None, data: dict) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gr_records(kind,id,tenant,status,data) VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT(kind,id) DO UPDATE SET tenant=excluded.tenant,status=excluded.status,data=excluded.data,updated_at=now()",
                (kind, record_id, tenant, status, self._json(data)),
            )

    def _get(self, kind: str, record_id: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM gr_records WHERE kind=%s AND id=%s", (kind, record_id))
            row = cur.fetchone()
        return row[0] if row else None

    def _list(self, kind: str, tenant: str | None = None, status: str | None = None) -> list[dict]:
        sql = "SELECT data FROM gr_records WHERE kind=%s"
        params: list = [kind]
        if tenant is not None:
            sql += " AND tenant=%s"
            params.append(tenant)
        if status is not None:
            sql += " AND status=%s"
            params.append(status)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [row[0] for row in rows]

    # ------------------------------------------------------------------ scopes
    def save_scope(self, scope: Scope) -> Scope:
        self._put("scope", scope.id, scope.tenant, scope.status, scope.to_dict())
        return scope

    def get_scope(self, scope_id: str) -> Scope | None:
        data = self._get("scope", scope_id)
        return Scope.from_dict(data) if data else None

    def list_scopes(self, tenant: str | None = None, status: str | None = None) -> list[Scope]:
        return sorted([Scope.from_dict(d) for d in self._list("scope", tenant, status)], key=lambda s: s.id)

    def set_scope_status(self, scope_id: str, status: str) -> Scope:
        scope = self.get_scope(scope_id)
        if not scope:
            raise KeyError(scope_id)
        scope.status = status
        return self.save_scope(scope)

    def save_plan(self, plan: MonitoringPlan) -> MonitoringPlan:
        self._put("plan", plan.scope_id, None, None, plan.to_dict())
        return plan

    def get_plan(self, scope_id: str) -> MonitoringPlan | None:
        data = self._get("plan", scope_id)
        return MonitoringPlan.from_dict(data) if data else None

    # ------------------------------------------------------------ acquisitions
    def save_acquisition(self, acquisition: Acquisition) -> Acquisition:
        self._put("acquisition", acquisition.id, None, acquisition.status, acquisition.to_dict())
        return acquisition

    def find_acquisition_by_key(self, key: str) -> Acquisition | None:
        for data in self._list("acquisition"):
            if data.get("idempotency_key") == key:
                return Acquisition.from_dict(data)
        return None

    def list_acquisitions(self, scope_id: str | None = None, limit: int = 100) -> list[Acquisition]:
        rows = [Acquisition.from_dict(d) for d in self._list("acquisition") if not scope_id or d.get("scope_id") == scope_id]
        return sorted(rows, key=lambda a: a.scheduled_for, reverse=True)[:limit]

    def last_received(self, scope_id: str) -> Acquisition | None:
        return next((a for a in self.list_acquisitions(scope_id, 200) if a.status == "received"), None)

    # ---------------------------------------------------------------- baselines
    def save_baseline(self, baseline: Baseline) -> Baseline:
        self._put("baseline", f"{baseline.scope_id}:{baseline.metric}", baseline.scope_id, None, baseline.to_dict())
        return baseline

    def get_baseline(self, scope_id: str, metric: str) -> Baseline | None:
        data = self._get("baseline", f"{scope_id}:{metric}")
        return Baseline.from_dict(data) if data else None

    def list_baselines(self, scope_id: str) -> list[Baseline]:
        return [Baseline.from_dict(d) for d in self._list("baseline", scope_id)]

    # ------------------------------------------------------------------- alerts
    def save_alert(self, alert: Alert) -> Alert:
        self._put("alert", alert.id, alert.tenant, alert.status, alert.to_dict())
        return alert

    def get_alert(self, alert_id: str) -> Alert | None:
        data = self._get("alert", alert_id)
        return Alert.from_dict(data) if data else None

    def list_alerts(self, tenant: str | None = None, scope_id: str | None = None, status: str | None = None, limit: int = 200) -> list[Alert]:
        rows = [Alert.from_dict(d) for d in self._list("alert", tenant, status)]
        if scope_id:
            rows = [a for a in rows if a.scope_id == scope_id]
        return sorted(rows, key=lambda a: a.created_at, reverse=True)[:limit]

    def count_alerts(self, tenant: str, since: str | None = None, status: str | None = None) -> int:
        return len([a for a in self.list_alerts(tenant, status=status, limit=100000) if not since or a.created_at >= since])

    def delete_alerts_before(self, cutoff: str, tenant: str | None = None) -> int:
        with self.conn.cursor() as cur:
            if tenant:
                cur.execute("DELETE FROM gr_records WHERE kind='alert' AND tenant=%s AND data->>'created_at' < %s", (tenant, cutoff))
            else:
                cur.execute("DELETE FROM gr_records WHERE kind='alert' AND data->>'created_at' < %s", (cutoff,))
            return cur.rowcount

    # ---------------------------------------------------------------- incidents
    def save_incident(self, incident: Incident) -> Incident:
        self._put("incident", incident.id, incident.tenant, incident.status, incident.to_dict())
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        data = self._get("incident", incident_id)
        return Incident.from_dict(data) if data else None

    def list_incidents(self, tenant: str | None = None, status: str | None = None) -> list[Incident]:
        return sorted([Incident.from_dict(d) for d in self._list("incident", tenant, status)], key=lambda i: i.opened_at, reverse=True)

    # ------------------------------------------------------------- notifications
    def save_notification(self, notification: Notification) -> Notification:
        self._put("notification", notification.id, notification.tenant, notification.status, notification.to_dict())
        return notification

    def list_notifications(self, status: str | None = None, tenant: str | None = None, limit: int = 500) -> list[Notification]:
        rows = [Notification.from_dict(d) for d in self._list("notification", tenant, status)]
        return sorted(rows, key=lambda n: n.created_at, reverse=True)[:limit]

    def due_notifications(self, at: datetime | None = None, limit: int = 100) -> list[Notification]:
        moment = (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        rows = [n for n in self.list_notifications(limit=10000) if n.status in {"queued", "failed"} and (not n.next_attempt_at or n.next_attempt_at <= moment)]
        return rows[:limit]

    # ------------------------------------------------------------------- models
    def save_model(self, entry: ModelEntry) -> ModelEntry:
        self._put("model", entry.name, None, entry.status, entry.to_dict())
        return entry

    def get_model(self, name: str) -> ModelEntry | None:
        data = self._get("model", name)
        return ModelEntry.from_dict(data) if data else None

    def list_models(self) -> list[ModelEntry]:
        return sorted([ModelEntry.from_dict(d) for d in self._list("model")], key=lambda m: m.name)

    # -------------------------------------------------------------- preferences
    def save_preferences(self, preferences: TenantPreferences) -> TenantPreferences:
        self._put("preference", preferences.tenant, preferences.tenant, None, preferences.to_dict())
        return preferences

    def get_preferences(self, tenant: str) -> TenantPreferences:
        data = self._get("preference", tenant)
        return TenantPreferences.from_dict(data) if data else TenantPreferences(tenant=tenant)

    # ------------------------------------------------------------------- costs
    def add_cost(self, entry: CostEntry) -> CostEntry:
        self._put("cost", entry.id, entry.tenant, None, entry.to_dict())
        return entry

    def costs(self, tenant: str, since: str | None = None, scope_id: str | None = None) -> list[CostEntry]:
        rows = [CostEntry(**d) for d in self._list("cost", tenant)]
        return [row for row in rows if (not since or row.at >= since) and (not scope_id or row.scope_id == scope_id)]

    def total_cost(self, tenant: str, since: str | None = None, scope_id: str | None = None) -> float:
        return round(sum(c.amount_eur for c in self.costs(tenant, since, scope_id)), 2)

    # -------------------------------------------------------------- validations
    def add_validation(self, record: ValidationRecord) -> ValidationRecord:
        self._put("validation", new_id("val"), record.scope_id, record.decision, record.to_dict())
        return record

    def validation_count(self, scope_id: str) -> int:
        return len([d for d in self._list("validation", scope_id)])

    def list_validations(self, scope_id: str) -> list[dict]:
        return self._list("validation", scope_id)

    # ---------------------------------------------------------------- forecasts
    def save_forecast(self, forecast: Forecast) -> Forecast:
        self._put("forecast", forecast.id, None, None, forecast.to_dict())
        return forecast

    def list_forecasts(self) -> list[Forecast]:
        return sorted([Forecast(**d) for d in self._list("forecast")], key=lambda f: f.issued_at, reverse=True)

    # ------------------------------------------------------------------- audit
    def audit(self, tenant: str, action: str, alert_id: str | None = None, actor: str | None = None, detail: dict | None = None) -> dict:
        previous = GENESIS
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM gr_records WHERE kind='audit' ORDER BY updated_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                previous = row[0]["hash"]
        event = {"tenant": tenant, "at": now_iso(), "action": action, "alert_id": alert_id, "actor": actor, "detail": detail or {}, "prev": previous}
        event["hash"] = hash_event(event)
        self._put("audit", f"{event['at']}:{new_id('e')}", tenant, None, event)
        return event

    def audit_events(self, tenant: str | None = None, limit: int = 500) -> list[dict]:
        rows = self._list("audit", tenant)
        return sorted(rows, key=lambda e: e["at"], reverse=True)[:limit]

    def verify_audit(self, tenant: str | None = None) -> tuple[bool, str]:
        events = sorted(self._list("audit", tenant), key=lambda e: e["at"])
        expected = GENESIS
        for event in events:
            if event.get("prev") != expected:
                return False, "broken link"
            if hash_event(event) != event.get("hash"):
                return False, "hash mismatch"
            expected = event["hash"]
        return True, f"{len(events)} events, chain intact"

    # ------------------------------------------------------------------- meta
    def meta_get(self, key: str, default: str | None = None) -> str | None:
        data = self._get("meta", key)
        return data.get("value", default) if data else default

    def meta_set(self, key: str, value: str) -> None:
        self._put("meta", key, None, None, {"value": value})

    # ---------------------------------------------------------------- lifecycle
    def purge(self, tenant: str, retention_days: int = 365, now: datetime | None = None) -> dict:
        cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        alerts = self.delete_alerts_before(cutoff, tenant)
        return {"alerts": alerts, "notifications": 0, "cutoff": cutoff}

    def stats(self, tenant: str) -> dict:
        return {
            "scopes": len(self.list_scopes(tenant)),
            "activeScopes": len(self.list_scopes(tenant, "active")),
            "alerts": len(self.list_alerts(tenant, limit=100000)),
            "openAlerts": len([a for a in self.list_alerts(tenant, limit=100000) if a.status in {"new", "acknowledged", "assigned", "investigating"}]),
            "incidents": len(self.list_incidents(tenant)),
            "notificationsQueued": len(self.list_notifications("queued", tenant)),
        }

    def close(self) -> None:
        self.conn.close()

    # Django-style helpers used by the API surface
    def backup(self, destination: str) -> str:
        raise NotImplementedError("Use pg_dump for PostgreSQL backups")

    def restore(self, source: str) -> None:
        raise NotImplementedError("Use pg_restore for PostgreSQL restores")


def build_store(dsn: str | None, fallback_path: str = "runtime/proactive.db") -> ProactiveStore | PostgresStore:
    if dsn:
        return PostgresStore(dsn)
    return ProactiveStore(fallback_path)
