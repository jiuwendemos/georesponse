from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from georesponse.api import app
from georesponse.proactive.models import Scope, new_id
from georesponse.proactive.store import ProactiveStore

client = TestClient(app)


def test_insight_endpoints_are_live():
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace("+00:00", "Z")
    for path in [
        f"/api/watch/since?ts={since}",
        "/api/watch/drift?days=30",
        "/api/watch/notifications/analytics",
        "/api/watch/feedback/summary",
        "/api/watch/production/worker/health",
    ]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert isinstance(response.json(), dict)


def test_alert_feedback_round_trip():
    alerts = client.get("/api/watch/alerts").json()
    alert_id = alerts[0]["id"]
    response = client.post(f"/api/watch/alerts/{alert_id}/feedback", json={"verdict": "useful", "note": "confirmed"})
    assert response.status_code == 200
    assert response.json()["feedback"]["verdict"] == "useful"
    listing = client.get(f"/api/watch/alerts/{alert_id}/feedback").json()
    assert listing["feedback"][0]["verdict"] == "useful"
    bad = client.post(f"/api/watch/alerts/{alert_id}/feedback", json={"verdict": "maybe"})
    assert bad.status_code == 422


def test_pause_requires_and_records_a_reason():
    scope_id = client.get("/api/watch/scopes").json()[0]["id"]
    paused = client.post(f"/api/watch/scopes/{scope_id}/pause?reason=maintenance")
    assert paused.status_code == 200
    assert paused.json()["reason"] == "maintenance"
    resumed = client.post(f"/api/watch/scopes/{scope_id}/resume?reason=done")
    assert resumed.status_code == 200
    audit = client.get("/api/watch/audit").json()
    events = audit.get("events", [])
    assert any(event.get("action") == "scope.paused" for event in events)


def test_audit_export_verifies_chain():
    response = client.get("/api/audit/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["x-audit-verified"] in {"true", "false"}


def test_multi_tenant_isolation():
    store = ProactiveStore(":memory:")
    for tenant in ("alpha", "beta"):
        store.save_scope(
            Scope(
                id=new_id("SC"),
                tenant=tenant,
                name=f"{tenant} site",
                kind="aoi",
                region="test",
                center=(7.0, 50.5),
                bbox=(6.9, 50.4, 7.1, 50.6),
                asset_class="infrastructure",
                change_types=["flood"],
                cadence="daily",
            )
        )
    assert {scope.tenant for scope in store.list_scopes("alpha")} == {"alpha"}
    assert {scope.tenant for scope in store.list_scopes("beta")} == {"beta"}
    store.close()
