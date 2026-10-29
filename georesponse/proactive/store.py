"""SQLite persistence for proactive monitoring.

One file, WAL mode, JSON rows.  The schema is intentionally boring so a pilot can
back it up with a file copy and an auditor can read it with `sqlite3`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..audit import GENESIS, hash_event
from .models import (
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
    dumps,
    loads,
    new_id,
    now_iso,
    parse_iso,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS scopes (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, status TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_scopes_tenant ON scopes(tenant, status);
CREATE TABLE IF NOT EXISTS plans (scope_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS acquisitions (id TEXT PRIMARY KEY, scope_id TEXT, status TEXT, scheduled_for TEXT, idempotency_key TEXT UNIQUE, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_acq_scope ON acquisitions(scope_id, scheduled_for);
CREATE TABLE IF NOT EXISTS baselines (scope_id TEXT, metric TEXT, json TEXT NOT NULL, PRIMARY KEY(scope_id, metric));
CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, tenant TEXT, scope_id TEXT, incident_id TEXT, status TEXT, created_at TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant, status, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_scope ON alerts(scope_id, status);
CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, tenant TEXT, scope_id TEXT, status TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_incidents_tenant ON incidents(tenant, status);
CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, tenant TEXT, alert_id TEXT, status TEXT, created_at TEXT, next_attempt_at TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_notifications_due ON notifications(status, next_attempt_at);
CREATE TABLE IF NOT EXISTS models (name TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preferences (tenant TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS costs (id TEXT PRIMARY KEY, tenant TEXT, scope_id TEXT, at TEXT, kind TEXT, amount_eur REAL, json TEXT);
CREATE TABLE IF NOT EXISTS validations (id INTEGER PRIMARY KEY AUTOINCREMENT, scope_id TEXT, analyst TEXT, alert_id TEXT, decision TEXT, at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS forecasts (id TEXT PRIMARY KEY, region TEXT, issued_at TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT, at TEXT, action TEXT, alert_id TEXT, actor TEXT, detail TEXT, prev TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, queue TEXT, status TEXT, payload TEXT, attempts INTEGER DEFAULT 0, available_at TEXT, created_at TEXT, updated_at TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(queue, status, available_at);
"""


class ProactiveStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            if self.path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.commit()

    # ------------------------------------------------------------------ scopes
    def save_scope(self, scope: Scope) -> Scope:
        with self._lock:
            self.conn.execute(
                "INSERT INTO scopes(id,tenant,status,json) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET tenant=excluded.tenant,status=excluded.status,json=excluded.json",
                (scope.id, scope.tenant, scope.status, dumps(scope.to_dict())),
            )
            self.conn.commit()
        return scope

    def get_scope(self, scope_id: str) -> Scope | None:
        row = self.conn.execute("SELECT json FROM scopes WHERE id=?", (scope_id,)).fetchone()
        return Scope.from_dict(loads(row["json"])) if row else None

    def list_scopes(self, tenant: str | None = None, status: str | None = None) -> list[Scope]:
        sql = "SELECT json FROM scopes WHERE 1=1"
        params: list = []
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY id"
        return [Scope.from_dict(loads(row["json"])) for row in self.conn.execute(sql, params)]

    def set_scope_status(self, scope_id: str, status: str) -> Scope:
        scope = self.get_scope(scope_id)
        if scope is None:
            raise KeyError(f"unknown scope: {scope_id}")
        scope.status = status
        return self.save_scope(scope)

    def save_plan(self, plan: MonitoringPlan) -> MonitoringPlan:
        with self._lock:
            self.conn.execute(
                "INSERT INTO plans(scope_id,json) VALUES(?,?) ON CONFLICT(scope_id) DO UPDATE SET json=excluded.json",
                (plan.scope_id, dumps(plan.to_dict())),
            )
            self.conn.commit()
        return plan

    def get_plan(self, scope_id: str) -> MonitoringPlan | None:
        row = self.conn.execute("SELECT json FROM plans WHERE scope_id=?", (scope_id,)).fetchone()
        return MonitoringPlan.from_dict(loads(row["json"])) if row else None

    # ------------------------------------------------------------ acquisitions
    def save_acquisition(self, acquisition: Acquisition) -> Acquisition:
        with self._lock:
            self.conn.execute(
                "INSERT INTO acquisitions(id,scope_id,status,scheduled_for,idempotency_key,json) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status,json=excluded.json",
                (
                    acquisition.id,
                    acquisition.scope_id,
                    acquisition.status,
                    acquisition.scheduled_for,
                    acquisition.idempotency_key,
                    dumps(acquisition.to_dict()),
                ),
            )
            self.conn.commit()
        return acquisition

    def find_acquisition_by_key(self, key: str) -> Acquisition | None:
        row = self.conn.execute("SELECT json FROM acquisitions WHERE idempotency_key=?", (key,)).fetchone()
        return Acquisition.from_dict(loads(row["json"])) if row else None

    def list_acquisitions(self, scope_id: str | None = None, limit: int = 100) -> list[Acquisition]:
        sql = "SELECT json FROM acquisitions"
        params: list = []
        if scope_id:
            sql += " WHERE scope_id=?"
            params.append(scope_id)
        sql += " ORDER BY scheduled_for DESC LIMIT ?"
        params.append(limit)
        return [Acquisition.from_dict(loads(row["json"])) for row in self.conn.execute(sql, params)]

    def last_received(self, scope_id: str) -> Acquisition | None:
        rows = self.list_acquisitions(scope_id, 100)
        for item in rows:
            if item.status == "received":
                return item
        return None

    # ---------------------------------------------------------------- baselines
    def save_baseline(self, baseline: Baseline) -> Baseline:
        with self._lock:
            self.conn.execute(
                "INSERT INTO baselines(scope_id,metric,json) VALUES(?,?,?) "
                "ON CONFLICT(scope_id,metric) DO UPDATE SET json=excluded.json",
                (baseline.scope_id, baseline.metric, dumps(baseline.to_dict())),
            )
            self.conn.commit()
        return baseline

    def get_baseline(self, scope_id: str, metric: str) -> Baseline | None:
        row = self.conn.execute(
            "SELECT json FROM baselines WHERE scope_id=? AND metric=?", (scope_id, metric)
        ).fetchone()
        return Baseline.from_dict(loads(row["json"])) if row else None

    def list_baselines(self, scope_id: str) -> list[Baseline]:
        return [
            Baseline.from_dict(loads(row["json"]))
            for row in self.conn.execute("SELECT json FROM baselines WHERE scope_id=? ORDER BY metric", (scope_id,))
        ]

    # ------------------------------------------------------------------- alerts
    def save_alert(self, alert: Alert) -> Alert:
        with self._lock:
            self.conn.execute(
                "INSERT INTO alerts(id,tenant,scope_id,incident_id,status,created_at,json) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET incident_id=excluded.incident_id,status=excluded.status,json=excluded.json",
                (
                    alert.id,
                    alert.tenant,
                    alert.scope_id,
                    alert.incident_id,
                    alert.status,
                    alert.created_at,
                    dumps(alert.to_dict()),
                ),
            )
            self.conn.commit()
        return alert

    def get_alert(self, alert_id: str) -> Alert | None:
        row = self.conn.execute("SELECT json FROM alerts WHERE id=?", (alert_id,)).fetchone()
        return Alert.from_dict(loads(row["json"])) if row else None

    def list_alerts(
        self,
        tenant: str | None = None,
        scope_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[Alert]:
        sql = "SELECT json FROM alerts WHERE 1=1"
        params: list = []
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        if scope_id:
            sql += " AND scope_id=?"
            params.append(scope_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [Alert.from_dict(loads(row["json"])) for row in self.conn.execute(sql, params)]

    def count_alerts(self, tenant: str, since: str | None = None, status: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM alerts WHERE tenant=?"
        params: list = [tenant]
        if since:
            sql += " AND created_at>=?"
            params.append(since)
        if status:
            sql += " AND status=?"
            params.append(status)
        return int(self.conn.execute(sql, params).fetchone()["n"])

    def delete_alerts_before(self, cutoff: str, tenant: str | None = None) -> int:
        sql = "DELETE FROM alerts WHERE created_at<?"
        params: list = [cutoff]
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        with self._lock:
            cursor = self.conn.execute(sql, params)
            self.conn.commit()
        return cursor.rowcount

    # ---------------------------------------------------------------- incidents
    def save_incident(self, incident: Incident) -> Incident:
        with self._lock:
            self.conn.execute(
                "INSERT INTO incidents(id,tenant,scope_id,status,json) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status,json=excluded.json",
                (incident.id, incident.tenant, incident.scope_id, incident.status, dumps(incident.to_dict())),
            )
            self.conn.commit()
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self.conn.execute("SELECT json FROM incidents WHERE id=?", (incident_id,)).fetchone()
        return Incident.from_dict(loads(row["json"])) if row else None

    def list_incidents(self, tenant: str | None = None, status: str | None = None) -> list[Incident]:
        sql = "SELECT json FROM incidents WHERE 1=1"
        params: list = []
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY json_extract(json,'$.opened_at') DESC"
        return [Incident.from_dict(loads(row["json"])) for row in self.conn.execute(sql, params)]

    # ------------------------------------------------------------- notifications
    def save_notification(self, notification: Notification) -> Notification:
        with self._lock:
            self.conn.execute(
                "INSERT INTO notifications(id,tenant,alert_id,status,created_at,next_attempt_at,json) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status,next_attempt_at=excluded.next_attempt_at,json=excluded.json",
                (
                    notification.id,
                    notification.tenant,
                    notification.alert_id,
                    notification.status,
                    notification.created_at,
                    notification.next_attempt_at,
                    dumps(notification.to_dict()),
                ),
            )
            self.conn.commit()
        return notification

    def list_notifications(self, status: str | None = None, tenant: str | None = None, limit: int = 500) -> list[Notification]:
        sql = "SELECT json FROM notifications WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if tenant:
            sql += " AND tenant=?"
            params.append(tenant)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [Notification.from_dict(loads(row["json"])) for row in self.conn.execute(sql, params)]

    def due_notifications(self, at: datetime | None = None, limit: int = 100) -> list[Notification]:
        moment = (at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT json FROM notifications WHERE status IN ('queued','failed') AND (next_attempt_at IS NULL OR next_attempt_at<=?) "
            "ORDER BY created_at LIMIT ?",
            (moment, limit),
        )
        return [Notification.from_dict(loads(row["json"])) for row in rows]

    # ------------------------------------------------------------------- models
    def save_model(self, entry: ModelEntry) -> ModelEntry:
        with self._lock:
            self.conn.execute(
                "INSERT INTO models(name,json) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET json=excluded.json",
                (entry.name, dumps(entry.to_dict())),
            )
            self.conn.commit()
        return entry

    def get_model(self, name: str) -> ModelEntry | None:
        row = self.conn.execute("SELECT json FROM models WHERE name=?", (name,)).fetchone()
        return ModelEntry.from_dict(loads(row["json"])) if row else None

    def list_models(self) -> list[ModelEntry]:
        return [ModelEntry.from_dict(loads(row["json"])) for row in self.conn.execute("SELECT json FROM models ORDER BY name")]

    # -------------------------------------------------------------- preferences
    def save_preferences(self, preferences: TenantPreferences) -> TenantPreferences:
        with self._lock:
            self.conn.execute(
                "INSERT INTO preferences(tenant,json) VALUES(?,?) ON CONFLICT(tenant) DO UPDATE SET json=excluded.json",
                (preferences.tenant, dumps(preferences.to_dict())),
            )
            self.conn.commit()
        return preferences

    def get_preferences(self, tenant: str) -> TenantPreferences:
        row = self.conn.execute("SELECT json FROM preferences WHERE tenant=?", (tenant,)).fetchone()
        return TenantPreferences.from_dict(loads(row["json"])) if row else TenantPreferences(tenant=tenant)

    # ------------------------------------------------------------------- costs
    def add_cost(self, entry: CostEntry) -> CostEntry:
        with self._lock:
            self.conn.execute(
                "INSERT INTO costs(id,tenant,scope_id,at,kind,amount_eur,json) VALUES(?,?,?,?,?,?,?)",
                (entry.id, entry.tenant, entry.scope_id, entry.at, entry.kind, entry.amount_eur, dumps(entry.to_dict())),
            )
            self.conn.commit()
        return entry

    def costs(self, tenant: str, since: str | None = None, scope_id: str | None = None) -> list[CostEntry]:
        sql = "SELECT json FROM costs WHERE tenant=?"
        params: list = [tenant]
        if since:
            sql += " AND at>=?"
            params.append(since)
        if scope_id:
            sql += " AND scope_id=?"
            params.append(scope_id)
        return [CostEntry(**loads(row["json"])) for row in self.conn.execute(sql, params)]

    def total_cost(self, tenant: str, since: str | None = None, scope_id: str | None = None) -> float:
        return round(sum(item.amount_eur for item in self.costs(tenant, since, scope_id)), 2)

    # -------------------------------------------------------------- validations
    def add_validation(self, record: ValidationRecord) -> ValidationRecord:
        with self._lock:
            self.conn.execute(
                "INSERT INTO validations(scope_id,analyst,alert_id,decision,at,note) VALUES(?,?,?,?,?,?)",
                (record.scope_id, record.analyst, record.alert_id, record.decision, record.at, record.note),
            )
            self.conn.commit()
        return record

    def validation_count(self, scope_id: str) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) AS n FROM validations WHERE scope_id=?", (scope_id,)).fetchone()["n"]
        )

    def list_validations(self, scope_id: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM validations WHERE scope_id=? ORDER BY id", (scope_id,))]

    # ---------------------------------------------------------------- forecasts
    def save_forecast(self, forecast: Forecast) -> Forecast:
        with self._lock:
            self.conn.execute(
                "INSERT INTO forecasts(id,region,issued_at,json) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
                (forecast.id, forecast.region, forecast.issued_at, dumps(forecast.to_dict())),
            )
            self.conn.commit()
        return forecast

    def list_forecasts(self) -> list[Forecast]:
        return [Forecast(**loads(row["json"])) for row in self.conn.execute("SELECT json FROM forecasts ORDER BY issued_at DESC")]

    # ------------------------------------------------------------------- audit
    def audit(self, tenant: str, action: str, alert_id: str | None = None, actor: str | None = None, detail: dict | None = None) -> dict:
        previous = GENESIS
        row = self.conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            previous = row["hash"]
        event = {
            "tenant": tenant,
            "at": now_iso(),
            "action": action,
            "alert_id": alert_id,
            "actor": actor,
            "detail": detail or {},
            "prev": previous,
        }
        event["hash"] = hash_event(event)
        with self._lock:
            self.conn.execute(
                "INSERT INTO audit(tenant,at,action,alert_id,actor,detail,prev,hash) VALUES(?,?,?,?,?,?,?,?)",
                (
                    tenant,
                    event["at"],
                    action,
                    alert_id,
                    actor,
                    dumps(event["detail"]),
                    previous,
                    event["hash"],
                ),
            )
            self.conn.commit()
        return event

    def audit_events(self, tenant: str | None = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM audit"
        params: list = []
        if tenant:
            sql += " WHERE tenant=?"
            params.append(tenant)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in self.conn.execute(sql, params)]

    def verify_audit(self, tenant: str | None = None) -> tuple[bool, str]:
        rows = list(self.conn.execute("SELECT * FROM audit WHERE (? IS NULL OR tenant=?) ORDER BY id", (tenant, tenant)))
        expected_prev = GENESIS
        for row in rows:
            if row["prev"] != expected_prev:
                return False, f"audit {row['id']}: broken link"
            event = {
                "tenant": row["tenant"],
                "at": row["at"],
                "action": row["action"],
                "alert_id": row["alert_id"],
                "actor": row["actor"],
                "detail": json.loads(row["detail"]),
                "prev": row["prev"],
            }
            if hash_event(event) != row["hash"]:
                return False, f"audit {row['id']}: hash mismatch"
            expected_prev = row["hash"]
        return True, f"{len(rows)} events, chain intact"

    # ------------------------------------------------------------------ backup
    def backup(self, destination: str | Path) -> str:
        destination = str(destination)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self.conn.backup(target)
            finally:
                target.close()
        return destination

    def restore(self, source: str | Path) -> None:
        source_conn = sqlite3.connect(str(source))
        try:
            with self._lock:
                source_conn.backup(self.conn)
        finally:
            source_conn.close()

    def purge(self, tenant: str, retention_days: int = 365, now: datetime | None = None) -> dict:
        cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=retention_days)).isoformat(timespec="seconds")
        with self._lock:
            alerts = self.conn.execute("DELETE FROM alerts WHERE tenant=? AND created_at<?", (tenant, cutoff)).rowcount
            notifications = self.conn.execute(
                "DELETE FROM notifications WHERE tenant=? AND created_at<?", (tenant, cutoff)
            ).rowcount
            self.conn.commit()
        return {"alerts": alerts, "notifications": notifications, "cutoff": cutoff}

    # ------------------------------------------------------------------- stats
    def stats(self, tenant: str) -> dict:
        return {
            "scopes": len(self.list_scopes(tenant)),
            "activeScopes": len(self.list_scopes(tenant, "active")),
            "alerts": self.count_alerts(tenant),
            "openAlerts": len(
                [a for a in self.list_alerts(tenant) if a.status in {"new", "acknowledged", "assigned", "investigating"}]
            ),
            "incidents": len(self.list_incidents(tenant)),
            "notificationsQueued": len(self.list_notifications("queued", tenant)),
        }

    def meta_get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def meta_set(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def ensure_demo_scope(tenant: str = "demo") -> tuple[Scope, MonitoringPlan]:
    scope = Scope(
        id="scope-ahr-corridor",
        tenant=tenant,
        name="Ahr corridor watch",
        kind="corridor",
        region="Ahrweiler, Germany",
        center=(7.10, 50.545),
        bbox=(7.043, 50.522, 7.157, 50.567),
        asset_class="utility + emergency",
        change_types=["flood", "erosion", "construction"],
        cadence="daily",
        priority=1,
        subscription_tier="daily",
        freshness_slo_hours=24,
    )
    plan = MonitoringPlan(scope_id=scope.id, cadence="daily", recipients=["ops@example.com"], digest="instant")
    return scope, plan


def count_since(store: ProactiveStore, tenant: str, hours: int) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    return store.count_alerts(tenant, since=since)


def serialize_rows(rows: Iterable[dict]) -> list[dict]:
    return [dict(row) for row in rows]
