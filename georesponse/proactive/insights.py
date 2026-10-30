"""Operator insights: what changed, drift, notification analytics and feedback.

These are the small, factual answers an operator needs between ticks:
what happened since I last looked, is a scope behaving unusually, and are
notifications actually being delivered and acknowledged.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .models import now_iso, parse_iso, utcnow
from .store import ProactiveStore

OPEN_STATUSES = {"new", "acknowledged", "assigned", "investigating"}
FEEDBACK_VERDICTS = {"useful", "not_useful", "wrong"}


def _since(value: str | None, *, default_hours: int = 24) -> str:
    if value:
        parse_iso(value)  # validate
        return value
    return (utcnow() - timedelta(hours=default_hours)).isoformat(timespec="seconds")


def what_changed(store: ProactiveStore, tenant: str, *, since: str | None = None, limit: int = 200) -> dict:
    """Everything that moved after ``since`` (default: 24 hours)."""
    cutoff = _since(since)
    alerts = [a for a in store.list_alerts(tenant, limit=1000) if a.created_at >= cutoff]
    incidents = [i for i in store.list_incidents(tenant) if i.opened_at >= cutoff]
    notifications = [n for n in store.list_notifications(tenant=tenant, limit=1000) if n.created_at >= cutoff]
    sent = [n for n in notifications if n.status == "sent"]
    resolved = [a for a in store.list_alerts(tenant, limit=1000) if a.status in {"resolved", "dismissed"} and (a.updated_at or a.created_at) >= cutoff]
    return {
        "tenant": tenant,
        "since": cutoff,
        "generatedAt": now_iso(),
        "counts": {
            "newAlerts": len(alerts),
            "openAlerts": len([a for a in store.list_alerts(tenant, limit=1000) if a.status in OPEN_STATUSES]),
            "incidents": len(incidents),
            "notifications": len(notifications),
            "sent": len(sent),
            "closed": len(resolved),
        },
        "alerts": [a.to_dict() for a in sorted(alerts, key=lambda a: a.created_at, reverse=True)[:limit]],
        "incidents": [i.to_dict() for i in sorted(incidents, key=lambda i: i.opened_at, reverse=True)[:limit]],
        "closed": [a.to_dict() for a in sorted(resolved, key=lambda a: a.updated_at or a.created_at, reverse=True)[:limit]],
    }


def drift(store: ProactiveStore, tenant: str, *, days: int = 14) -> dict:
    """Compare each scope's alert rate in the last window with the one before.

    A scope is flagged when it is spiking, silent after being active, or
    emerging from no history. This is a health signal, not a model change.
    """
    now = utcnow()
    current_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)
    alerts = store.list_alerts(tenant, limit=10000)
    rows = []
    for scope in store.list_scopes(tenant):
        scope_alerts = [a for a in alerts if a.scope_id == scope.id]
        current = [a for a in scope_alerts if parse_iso(a.created_at) >= current_start]
        previous = [a for a in scope_alerts if previous_start <= parse_iso(a.created_at) < current_start]
        c, p = len(current), len(previous)
        if p == 0 and c >= 3:
            status = "emerging"
        elif p >= 3 and c == 0:
            status = "silent"
        elif p > 0 and c >= max(3, p * 2):
            status = "spike"
        elif p > 0 and c <= p * 0.4:
            status = "quiet"
        else:
            status = "stable"
        rows.append({
            "scopeId": scope.id,
            "name": scope.name,
            "current": c,
            "previous": p,
            "ratio": round(c / p, 2) if p else None,
            "status": status,
        })
    flagged = [row for row in rows if row["status"] in {"emerging", "silent", "spike"}]
    return {
        "tenant": tenant,
        "windowDays": days,
        "generatedAt": now_iso(),
        "scopes": rows,
        "flagged": flagged,
    }


def notification_analytics(store: ProactiveStore, tenant: str) -> dict:
    """Delivery health: what was sent, what failed, and how long it took."""
    notifications = store.list_notifications(tenant=tenant, limit=5000)
    by_status: dict[str, int] = {}
    by_channel: dict[str, dict[str, int]] = {}
    latencies: list[float] = []
    for notification in notifications:
        by_status[notification.status] = by_status.get(notification.status, 0) + 1
        channel = by_channel.setdefault(notification.channel, {})
        channel[notification.status] = channel.get(notification.status, 0) + 1
        if notification.status == "sent" and notification.sent_at:
            try:
                delta = (parse_iso(notification.sent_at) - parse_iso(notification.created_at)).total_seconds()
                if delta >= 0:
                    latencies.append(delta)
            except ValueError:
                continue
    total = len(notifications)
    sent = by_status.get("sent", 0)
    return {
        "tenant": tenant,
        "generatedAt": now_iso(),
        "total": total,
        "byStatus": by_status,
        "byChannel": by_channel,
        "deliveryRate": round(sent / total, 3) if total else None,
        "deadLetters": by_status.get("dead", 0),
        "averageSendSeconds": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "maxSendSeconds": round(max(latencies), 1) if latencies else None,
    }


def record_feedback(
    store: ProactiveStore,
    alert_id: str,
    verdict: str,
    *,
    note: str = "",
    actor: str = "analyst",
) -> dict:
    """Capture whether an alert was useful. Feeds the quality loop, never a model write."""
    alert = store.get_alert(alert_id)
    if alert is None:
        raise KeyError(alert_id)
    if verdict not in FEEDBACK_VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(FEEDBACK_VERDICTS)}")
    key = f"alert-feedback:{alert_id}"
    history = alert_feedback(store, alert_id)
    entry = {"at": now_iso(), "verdict": verdict, "note": note, "actor": actor, "alertId": alert_id}
    history.append(entry)
    store.meta_set(key, json.dumps(history, ensure_ascii=False))
    store.audit(alert.tenant, "alert.feedback", alert_id=alert_id, actor=actor, detail={"verdict": verdict, "note": note})
    return {"alertId": alert_id, "feedback": entry, "history": history}


def alert_feedback(store: ProactiveStore, alert_id: str) -> list[dict]:
    raw = store.meta_get(f"alert-feedback:{alert_id}")
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def feedback_summary(store: ProactiveStore, tenant: str) -> dict:
    alerts = store.list_alerts(tenant, limit=10000)
    counts = {key: 0 for key in FEEDBACK_VERDICTS}
    for alert in alerts:
        for entry in alert_feedback(store, alert.id):
            verdict = entry.get("verdict")
            if verdict in counts:
                counts[verdict] += 1
    total = sum(counts.values())
    return {
        "tenant": tenant,
        "counts": counts,
        "total": total,
        "usefulRate": round(counts["useful"] / total, 3) if total else None,
    }


def worker_health(heartbeat_path: str, *, stale_after_seconds: int = 1800) -> dict:
    """Read the worker heartbeat written on every tick."""
    try:
        with open(heartbeat_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {"ok": False, "detail": "no heartbeat yet", "path": heartbeat_path}
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "detail": str(exc), "path": heartbeat_path}
    at = payload.get("at")
    age = None
    if at:
        try:
            age = (datetime.now(timezone.utc) - parse_iso(at)).total_seconds()
        except ValueError:
            age = None
    return {
        "ok": age is not None and age <= stale_after_seconds,
        "path": heartbeat_path,
        "ageSeconds": round(age, 1) if age is not None else None,
        "staleAfterSeconds": stale_after_seconds,
        "heartbeat": payload,
    }
