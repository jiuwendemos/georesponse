"""Operational helpers: quotas, secrets, load tests, blue/green, retention."""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import Acquisition, Alert, CostEntry, MonitoringPlan, Scope, new_id, now_iso, utcnow
from .scheduler import plan_batch
from .store import ProactiveStore


class QuotaError(PermissionError):
    pass


@dataclass
class TenantQuota:
    tenant: str
    max_scopes: int = 100
    max_alerts_per_day: int = 500
    max_cost_eur_per_month: float = 25_000
    max_recipients: int = 50


class QuotaManager:
    def __init__(self, store: ProactiveStore, quotas: dict[str, TenantQuota] | None = None) -> None:
        self.store = store
        self.quotas = quotas or {}
        self.default = TenantQuota(tenant="default")

    def quota(self, tenant: str) -> TenantQuota:
        return self.quotas.get(tenant, TenantQuota(tenant=tenant, **{k: v for k, v in self.default.__dict__.items() if k != "tenant"}))

    def check(self, tenant: str) -> dict:
        quota = self.quota(tenant)
        scopes = len(self.store.list_scopes(tenant))
        day_ago = (utcnow() - timedelta(days=1)).isoformat(timespec="seconds")
        alerts = self.store.count_alerts(tenant, since=day_ago)
        month_start = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        cost = self.store.total_cost(tenant, since=month_start)
        violations = []
        if scopes >= quota.max_scopes:
            violations.append("max_scopes")
        if alerts >= quota.max_alerts_per_day:
            violations.append("max_alerts_per_day")
        if cost >= quota.max_cost_eur_per_month:
            violations.append("max_cost_eur_per_month")
        return {
            "tenant": tenant,
            "scopes": scopes,
            "alerts24h": alerts,
            "costMonthEur": round(cost, 2),
            "quota": quota.__dict__,
            "violations": violations,
            "ok": not violations,
        }

    def enforce(self, tenant: str) -> None:
        result = self.check(tenant)
        if not result["ok"]:
            raise QuotaError(f"tenant quota exceeded: {result['violations']}")


class SecretVault:
    """File-backed secret vault for demo/air-gapped deployments.

    Production should swap this for the customer's KMS or Vault.  Files are
    written with owner-only permissions.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_.")
        return self.root / f"{safe}.json"

    def put(self, name: str, payload: dict) -> Path:
        path = self._path(name)
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def get(self, name: str) -> dict:
        path = self._path(name)
        if not path.exists():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def rotate(self, name: str, payload: dict) -> dict:
        previous = self.get(name) if self._path(name).exists() else {}
        self.put(name, payload)
        return {"name": name, "rotatedAt": now_iso(), "previousKeys": sorted(previous)}


def batch_windows(acquisitions: Iterable[Acquisition], *, window_hours: int = 6, batch_size: int = 8) -> list[dict]:
    """Align NPU work to acquisition windows rather than per-image bursts."""
    buckets: dict[int, list[Acquisition]] = {}
    for acquisition in acquisitions:
        moment = datetime.fromisoformat(acquisition.scheduled_for.replace("Z", "+00:00"))
        bucket = int(moment.timestamp() // (window_hours * 3600))
        buckets.setdefault(bucket, []).append(acquisition)
    windows = []
    for bucket, items in sorted(buckets.items()):
        for start in range(0, len(items), batch_size):
            windows.append(
                {
                    "windowStart": datetime.fromtimestamp(bucket * window_hours * 3600, tz=timezone.utc).isoformat(timespec="seconds"),
                    "items": [a.id for a in items[start : start + batch_size]],
                    "batchSize": batch_size,
                    "npuProfile": "ascend-310p-demo",
                }
            )
    return windows


def run_airgap(store: ProactiveStore, mappings: dict[str, str | Path]) -> dict:
    from .scheduler import import_airgap

    imported = {}
    for scope_id, folder in mappings.items():
        items = import_airgap(store, scope_id, folder)
        imported[scope_id] = [item.id for item in items]
    return {"imported": imported, "at": now_iso()}


def replay(store: ProactiveStore, acquisition_id: str, *, actor: str = "ops") -> Acquisition:
    acquisition = next((a for a in store.list_acquisitions(limit=2000) if a.id == acquisition_id), None)
    if acquisition is None:
        raise KeyError(acquisition_id)
    acquisition.status = "planned"
    acquisition.attempts = 0
    acquisition.next_attempt_at = None
    store.save_acquisition(acquisition)
    store.audit("demo", "acquisition.replay", actor=actor, detail={"acquisition": acquisition.id})
    return acquisition


def backup_restore_drill(store: ProactiveStore, workdir: str | Path) -> dict:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    before = store.stats("demo")
    backup = workdir / "proactive-drill.db"
    store.backup(backup)
    store.audit("demo", "drill.mutation", actor="drill")
    store.restore(backup)
    after = store.stats("demo")
    verified = store.verify_audit("demo")[0]
    return {
        "backup": str(backup),
        "before": before,
        "after": after,
        "auditVerified": verified,
        "ok": before["scopes"] == after["scopes"] and verified,
        "at": now_iso(),
    }


def load_test(*, scopes: int = 1000, alerts_per_scope: int = 2) -> dict:
    """Synthetic throughput check. 1,000 scopes is the deployment target."""
    store = ProactiveStore(":memory:")
    started = time.perf_counter()
    for index in range(scopes):
        scope = Scope(
            id=f"load-{index:05d}",
            tenant="load",
            name=f"Load scope {index}",
            kind="aoi",
            region="Load region",
            center=(7.0, 50.0),
            bbox=(6.99, 49.99, 7.01, 50.01),
            asset_class="utility",
            change_types=["flood"],
            cadence="weekly",
            priority=3,
        )
        store.save_scope(scope)
        store.save_plan(MonitoringPlan(scope_id=scope.id, cadence="weekly"))
    scope_seconds = time.perf_counter() - started
    alert_started = time.perf_counter()
    for index in range(scopes):
        for item in range(alerts_per_scope):
            alert = Alert(
                id=f"AL-{index:05d}-{item}",
                tenant="load",
                scope_id=f"load-{index:05d}",
                title="Load alert",
                summary="Synthetic alert for the load test.",
                severity="orange",
                urgency=0.5,
                confidence=0.8,
                change_type="flood",
                observed=0.1,
                baseline=0.02,
                lon=7.0,
                lat=50.0,
            )
            store.save_alert(alert)
    alert_seconds = time.perf_counter() - alert_started
    batch = plan_batch(store, "load", limit=500)
    stats = store.stats("load")
    result = {
        "scopes": scopes,
        "alerts": stats["alerts"],
        "scopeWriteMs": round(scope_seconds * 1000, 1),
        "alertWriteMs": round(alert_seconds * 1000, 1),
        "alertsPerSecond": round((scopes * alerts_per_scope) / max(alert_seconds, 0.001), 1),
        "batchSize": len(batch),
        "ok": stats["scopes"] == scopes and stats["alerts"] == scopes * alerts_per_scope,
        "target": "1,000 scopes / 10,000 alerts/day",
        "at": now_iso(),
    }
    store.close()
    return result


@dataclass
class Deployment:
    color: str = "blue"
    version: str = "1.4.2"
    previous: str = "1.3.9"
    promoted_at: str = field(default_factory=now_iso)
    state: str = "stable"


class BlueGreen:
    def __init__(self, store: ProactiveStore) -> None:
        self.store = store

    def current(self) -> dict:
        raw = self.store.meta_get("deployment")
        if not raw:
            deployment = Deployment()
            self.store.meta_set("deployment", json.dumps(deployment.__dict__))
            return deployment.__dict__
        return json.loads(raw)

    def promote(self, version: str, *, actor: str = "mlops") -> dict:
        current = self.current()
        deployment = Deployment(
            color="green" if current["color"] == "blue" else "blue",
            version=version,
            previous=current["version"],
            state="stable",
        )
        self.store.meta_set("deployment", json.dumps(deployment.__dict__))
        self.store.audit("demo", "deployment.promoted", actor=actor, detail={"version": version, "color": deployment.color})
        return deployment.__dict__

    def rollback(self, *, actor: str = "mlops") -> dict:
        current = self.current()
        deployment = Deployment(
            color="blue" if current["color"] == "green" else "green",
            version=current["previous"],
            previous=current["version"],
            state="rolled-back",
        )
        self.store.meta_set("deployment", json.dumps(deployment.__dict__))
        self.store.audit("demo", "deployment.rollback", actor=actor, detail={"version": deployment.version})
        return deployment.__dict__



class JobQueue:
    """SQLite-backed job queue with retries and a dead-letter list.

    It is small enough for an edge box and has the semantics a worker needs:
    claim, complete, fail with backoff, replay, dead-letter inspection.
    """

    def __init__(self, store: ProactiveStore, *, max_attempts: int = 4) -> None:
        self.store = store
        self.max_attempts = max_attempts

    def enqueue(self, queue: str, payload: dict, *, available_at: str | None = None) -> str:
        job_id = new_id("job")
        now = now_iso()
        with self.store._lock:  # shared connection is guarded by the store lock
            self.store.conn.execute(
                "INSERT INTO jobs(id,queue,status,payload,attempts,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, queue, "queued", json.dumps(payload), 0, available_at or now, now, now),
            )
            self.store.conn.commit()
        return job_id

    def claim(self, queue: str, *, limit: int = 1, now: str | None = None) -> list[dict]:
        moment = now or now_iso()
        with self.store._lock:
            rows = list(
                self.store.conn.execute(
                    "SELECT * FROM jobs WHERE queue=? AND status='queued' AND available_at<=? ORDER BY created_at LIMIT ?",
                    (queue, moment, limit),
                )
            )
            claimed = []
            for row in rows:
                self.store.conn.execute(
                    "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                    (moment, row["id"]),
                )
                claimed.append({**dict(row), "payload": json.loads(row["payload"]), "attempts": row["attempts"] + 1})
            self.store.conn.commit()
        return claimed

    def complete(self, job_id: str) -> None:
        with self.store._lock:
            self.store.conn.execute("UPDATE jobs SET status='done', updated_at=? WHERE id=?", (now_iso(), job_id))
            self.store.conn.commit()

    def fail(self, job_id: str, error: str) -> str:
        row = self.store.conn.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        attempts = int(row["attempts"])
        status = "dead" if attempts >= self.max_attempts else "queued"
        available = (utcnow() + timedelta(minutes=2 ** attempts)).isoformat(timespec="seconds")
        with self.store._lock:
            self.store.conn.execute(
                "UPDATE jobs SET status=?, error=?, available_at=?, updated_at=? WHERE id=?",
                (status, error, available, now_iso(), job_id),
            )
            self.store.conn.commit()
        return status

    def replay(self, job_id: str) -> None:
        with self.store._lock:
            self.store.conn.execute(
                "UPDATE jobs SET status='queued', attempts=0, available_at=?, error=NULL WHERE id=?",
                (now_iso(), job_id),
            )
            self.store.conn.commit()

    def stats(self, queue: str | None = None) -> dict:
        sql = "SELECT status, COUNT(*) AS n FROM jobs"
        params: list = []
        if queue:
            sql += " WHERE queue=?"
            params.append(queue)
        sql += " GROUP BY status"
        counts = {row["status"]: row["n"] for row in self.store.conn.execute(sql, params)}
        dead = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT id,queue,attempts,error FROM jobs WHERE status='dead' ORDER BY updated_at DESC LIMIT 50"
            )
        ]
        return {"counts": counts, "deadLetters": dead, "queue": queue}


class LocalObjectStore:
    """Content-addressed local object store; swap for S3/GCS in production."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("..", "_").lstrip("/")
        return self.root / safe

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise KeyError(key)
        return path.read_bytes()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self, prefix: str = "") -> list[dict]:
        base = self._path(prefix)
        if not base.exists():
            return []
        return [
            {"key": str(path.relative_to(self.root)).replace("\\", "/"), "bytes": path.stat().st_size, "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")}
            for path in sorted(base.rglob("*"))
            if path.is_file()
        ]

    def lifecycle(self, prefix: str, *, older_than_days: int, now: datetime | None = None) -> int:
        moment = now or utcnow()
        cutoff = moment.timestamp() - older_than_days * 86400
        removed = 0
        for item in self.list(prefix):
            path = self._path(item["key"])
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        return removed


class PostgresMirror:
    """Optional mirror to the production PostgreSQL schema.

    The demo writes SQLite; this class validates the target counts and performs a
    dry-run sync.  Set ``dsn`` and install psycopg to enable the live path.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn

    def sync(self, store: ProactiveStore, tenant: str) -> dict:
        scopes = store.list_scopes(tenant)
        alerts = store.list_alerts(tenant)
        incidents = store.list_incidents(tenant)
        payload = {
            "tenant": tenant,
            "scopes": len(scopes),
            "alerts": len(alerts),
            "incidents": len(incidents),
            "baselines": sum(len(store.list_baselines(scope.id)) for scope in scopes),
            "mode": "live" if self.dsn else "dry-run",
            "schema": "deploy/sql/postgres_schema.sql",
            "syncedAt": now_iso(),
        }
        if not self.dsn:
            return payload
        try:
            import psycopg  # type: ignore
            from psycopg.types.json import Json

            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cur:
                    for scope in scopes:
                        cur.execute(
                            "INSERT INTO scopes(id,tenant,status,payload) VALUES(%s,%s,%s,%s) "
                            "ON CONFLICT(id) DO UPDATE SET tenant=excluded.tenant,status=excluded.status,payload=excluded.payload",
                            (scope.id, scope.tenant, scope.status, Json(scope.to_dict())),
                        )
                        for baseline in store.list_baselines(scope.id):
                            cur.execute(
                                "INSERT INTO baselines(scope_id,metric,payload) VALUES(%s,%s,%s) "
                                "ON CONFLICT(scope_id,metric) DO UPDATE SET payload=excluded.payload",
                                (scope.id, baseline.metric, Json(baseline.to_dict())),
                            )
                    for incident in incidents:
                        cur.execute(
                            "INSERT INTO incidents(id,tenant,scope_id,status,opened_at,payload) VALUES(%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload",
                            (incident.id, incident.tenant, incident.scope_id, incident.status, incident.opened_at, Json(incident.to_dict())),
                        )
                    for alert in alerts:
                        cur.execute(
                            "INSERT INTO alerts(id,tenant,scope_id,incident_id,status,severity,created_at,sla_due,payload) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload",
                            (alert.id, alert.tenant, alert.scope_id, alert.incident_id, alert.status, alert.severity, alert.created_at, alert.sla_due, Json(alert.to_dict())),
                        )
                    cur.execute("SELECT count(*) FROM scopes WHERE tenant=%s", (tenant,))
                    payload["remoteScopes"] = cur.fetchone()[0]
                conn.commit()
            payload["ok"] = True
        except Exception as exc:  # noqa: BLE001
            payload["ok"] = False
            payload["error"] = str(exc)
        return payload
