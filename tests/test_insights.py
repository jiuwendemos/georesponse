import json
from datetime import datetime, timedelta, timezone

from georesponse.proactive.demo import seed_demo
from georesponse.proactive.insights import (
    alert_feedback,
    drift,
    feedback_summary,
    notification_analytics,
    record_feedback,
    what_changed,
    worker_health,
)
from georesponse.proactive.models import Notification, now_iso
from georesponse.proactive.store import ProactiveStore


def _store() -> ProactiveStore:
    store = ProactiveStore(":memory:")
    seed_demo(store)
    return store


def test_what_changed_returns_facts():
    store = _store()
    result = what_changed(store, "demo", since=(datetime.now(timezone.utc) - timedelta(days=365)).isoformat())
    assert result["counts"]["openAlerts"] > 0
    assert result["counts"]["newAlerts"] == len(result["alerts"])
    assert result["since"]

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    empty = what_changed(store, "demo", since=future)
    assert empty["counts"]["newAlerts"] == 0
    assert empty["alerts"] == []
    store.close()


def test_drift_reports_every_scope():
    store = _store()
    result = drift(store, "demo", days=30)
    scope_ids = {scope.id for scope in store.list_scopes("demo")}
    assert {row["scopeId"] for row in result["scopes"]} == scope_ids
    assert all(row["status"] in {"emerging", "silent", "spike", "quiet", "stable"} for row in result["scopes"])
    assert isinstance(result["flagged"], list)
    store.close()


def test_notification_analytics():
    store = _store()
    sent = Notification(
        id="NOT-A",
        tenant="demo",
        alert_id="ALT-X",
        channel="slack",
        recipient="ops",
        subject="Test",
        body="Body",
        status="sent",
        sent_at=now_iso(),
        created_at=(datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(timespec="seconds"),
    )
    dead = Notification(
        id="NOT-B",
        tenant="demo",
        alert_id="ALT-X",
        channel="email",
        recipient="ops@example.com",
        subject="Test",
        body="Body",
        status="dead",
    )
    store.save_notification(sent)
    store.save_notification(dead)
    result = notification_analytics(store, "demo")
    assert result["byStatus"]["sent"] >= 1
    assert result["byStatus"]["dead"] >= 1
    assert result["averageSendSeconds"] is not None
    assert 0 <= result["deliveryRate"] <= 1
    store.close()


def test_alert_feedback_and_summary():
    store = _store()
    alert = store.list_alerts("demo", limit=1)[0]
    record_feedback(store, alert.id, "useful", note="confirmed by adjuster")
    with_error = record_feedback(store, alert.id, "wrong", note="water reflection")
    assert len(with_error["history"]) == 2
    assert alert_feedback(store, alert.id)[0]["verdict"] == "useful"
    summary = feedback_summary(store, "demo")
    assert summary["counts"]["useful"] == 1
    assert summary["counts"]["wrong"] == 1
    try:
        record_feedback(store, alert.id, "maybe")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid verdict accepted")
    store.close()


def test_worker_health_reads_heartbeat(tmp_path):
    path = tmp_path / "heartbeat.json"
    assert worker_health(str(path))["ok"] is False
    path.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "status": "ok"}), encoding="utf-8")
    result = worker_health(str(path))
    assert result["ok"] is True
    assert result["heartbeat"]["status"] == "ok"
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    path.write_text(json.dumps({"at": old, "status": "ok"}), encoding="utf-8")
    assert worker_health(str(path), stale_after_seconds=60)["ok"] is False
