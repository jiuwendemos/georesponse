import json
from datetime import datetime, timedelta, timezone

import pytest

from georesponse.proactive import alerts as alert_ops
from georesponse.proactive import anticipation, integrations, notifications, scheduler
from georesponse.proactive.baseline import (
    BaselineEngine,
    apply_feedback,
    backtest,
    calibration,
    cross_sensor_confidence,
    detect_construction,
    detect_erosion,
    detect_vegetation,
    drift_score,
    suppression_factor,
    temporal_confirmation,
    trend_of,
)
from georesponse.proactive.demo import build_demo, seed_demo
from georesponse.proactive.engine import ProactiveEngine
from georesponse.proactive.governance import (
    KillSwitch,
    ModelRegistry,
    NonGoalError,
    OnCallSchedule,
    RateLimiter,
    TenantKeyring,
    ValidationGate,
    alert_quality,
    enforce_non_goal,
    explain_alert,
    false_alarm_cost,
    privacy_review_proactive,
    retention_policy,
)
from georesponse.proactive.integrations import dispatch_system
from georesponse.proactive.models import (
    Acquisition,
    Alert,
    Baseline,
    Forecast,
    MonitoringPlan,
    Scope,
    TenantPreferences,
    ValidationRecord,
    new_id,
)
from georesponse.proactive.store import ProactiveStore


@pytest.fixture()
def store():
    db = ProactiveStore(":memory:")
    yield db
    db.close()


@pytest.fixture()
def scope(store):
    scope = Scope(
        id="scope-test",
        tenant="tenant-a",
        name="Test corridor",
        kind="corridor",
        region="Test valley",
        center=(7.1, 50.5),
        bbox=(7.0, 50.4, 7.2, 50.6),
        asset_class="utility",
        change_types=["flood", "erosion"],
        cadence="daily",
        priority=1,
        freshness_slo_hours=24,
        metadata={"valueEur": 5_000_000, "population": 800, "assets": [{"id": "A1", "name": "Substation", "valueEur": 5_000_000, "population": 800, "critical": True, "groundM": 2.0}]},
    )
    store.save_scope(scope)
    store.save_plan(MonitoringPlan(scope_id=scope.id, cadence="daily", first_n_alerts_require_analyst=0, recipients=["ops@example.com"]))
    return scope


def test_scope_plan_and_isolation(store, scope):
    assert store.get_scope(scope.id).name == "Test corridor"
    assert store.list_scopes("tenant-a")[0].id == scope.id
    assert store.list_scopes("other") == []
    assert store.get_plan(scope.id).cadence == "daily"
    assert store.stats("tenant-a")["scopes"] == 1


def test_audit_chain_and_backup(store, scope, tmp_path):
    store.audit("tenant-a", "scope.created", actor="test")
    store.audit("tenant-a", "plan.updated", actor="test")
    ok, message = store.verify_audit("tenant-a")
    assert ok, message
    backup = store.backup(tmp_path / "backup.db")
    restored = ProactiveStore(backup)
    assert restored.get_scope(scope.id).name == "Test corridor"
    assert restored.verify_audit("tenant-a")[0]
    restored.close()


def test_baseline_and_detector(store, scope):
    engine = BaselineEngine(store)
    plan = store.get_plan(scope.id)
    store.save_baseline(Baseline(scope_id=scope.id, metric="change_fraction", values=[0.02, 0.03, 0.02, 0.04, 0.03]).recompute())
    engine.observe_and_store(
        scope,
        plan,
        {"changeFraction": 0.18, "confidence": 0.9, "cloud": 0.02, "changeType": "flood", "optical": True, "sar": True, "sarConfidence": 0.86},
    )
    finding = engine.observe_and_store(
        scope,
        plan,
        {"changeFraction": 0.2, "confidence": 0.9, "cloud": 0.02, "changeType": "flood", "optical": True, "sar": True, "sarConfidence": 0.86},
    )
    assert finding["alert"] is True
    assert finding["temporalConfirmation"] is True
    assert finding["confidence"] > 0.5
    assert store.get_baseline(scope.id, "change_fraction").values[-1] == 0.2


def test_suppression_blocks_alert(store, scope):
    engine = BaselineEngine(store)
    plan = store.get_plan(scope.id)
    store.save_baseline(Baseline(scope_id=scope.id, metric="change_fraction", values=[0.01, 0.02, 0.02]).recompute())
    finding = engine.evaluate(scope, plan, {"changeFraction": 0.2, "confidence": 0.9, "cloud": 0.95, "shadow": 0.9, "snow": 0.9})
    assert finding["alert"] is False


def test_baseline_helpers():
    assert trend_of([0.01, 0.02, 0.03]) == "increasing"
    assert temporal_confirmation([True, False, True], 2) is True
    assert cross_sensor_confidence(0.8, 0.8)["method"] == "optical+sar"
    assert suppression_factor(cloud=0.9) < 0.5
    assert detect_construction(0.1, 3)["alert"] is True
    assert detect_vegetation([0.7, 0.55])["alert"] is True
    assert detect_erosion([0.01, 0.03, 0.06])["alert"] is True
    assert drift_score([0.1] * 6, [0.5] * 6)["flag"] is True
    assert backtest([{"predicted": True, "actual": True, "confidence": 0.9}])["precision"] == 1
    assert any(row["n"] == 1 for row in calibration([0.9], [True]))


def test_feedback(store, scope):
    store.add_validation(ValidationRecord(scope_id=scope.id, analyst="a", alert_id="A", decision="rejected"))
    result = apply_feedback(store, scope)
    assert result["offset"] < 0


def test_scheduler_plan_idempotency_and_budget(store, scope):
    plan = store.get_plan(scope.id)
    first = scheduler.plan_acquisition(store, scope, plan)
    second = scheduler.plan_acquisition(store, scope, plan)
    assert first.id == second.id
    assert first.status == "ordered"
    forced = scheduler.watch_now(store, scope.id)
    assert forced.id != first.id
    plan.budget_eur_per_month = 0
    store.save_plan(plan)
    assert scheduler.plan_acquisition(store, scope, plan, force=True) is None


def test_scheduler_retry_receive_readiness(store, scope):
    plan = store.get_plan(scope.id)
    acquisition = scheduler.plan_acquisition(store, scope, plan)
    acquisition.status = "failed"
    store.save_acquisition(acquisition)
    retried = scheduler.retry(store, acquisition.id)
    assert retried.attempts == 1
    received = scheduler.receive(store, acquisition.id, scene_id="SCENE-1", cloud=0.1)
    assert received.status == "received"
    state = scheduler.readiness(store, scope, plan)
    assert state["score"] > 0.5
    assert scheduler.calendar(store, scope.id)
    assert scheduler.coverage(store, "tenant-a")[0]["coverageStatus"] == "ok"


def test_airgap_import(store, scope, tmp_path):
    (tmp_path / "ortho.tif").write_bytes(b"x")
    imported = scheduler.import_airgap(store, scope.id, tmp_path)
    assert len(imported) == 1
    assert imported[0].status == "received"


def test_cost_and_freshness(store, scope):
    plan = store.get_plan(scope.id)
    scheduler.plan_acquisition(store, scope, plan)
    report = scheduler.cost_report(store, "tenant-a")
    assert report["entries"] >= 1
    assert scheduler.freshness_slo(store, "tenant-a")["scopes"] == 1
    assert scheduler.blind_spots(store, "tenant-a")[0]["scopeId"] == scope.id


def test_forecast_watchlist_and_simulation(store, scope):
    forecast = anticipation.ingest_forecast({"region": "Test valley", "hazard": "flood", "probability": 0.8, "uncertainty": 0.2, "rainfallMm": 40})
    store.save_forecast(forecast)
    watch = anticipation.pre_event_watchlist(store, "tenant-a", [forecast])
    assert watch[0]["scopeId"] == scope.id
    assert watch[0]["taskingTrigger"] is True
    assert watch[0]["recommendation"]["teams"] >= 2
    assert anticipation.lead_time_hours(forecast) > 0
    assert anticipation.seasonal_calendar("Ahrweiler", 7)["risks"]
    assert anticipation.portfolio_heatmap(store, "tenant-a", [forecast])
    sim = anticipation.simulate_scenario(scope, water_level_m=3.0)
    assert sim["submerged"] >= 1
    assert anticipation.digest_since(store, "tenant-a")["periodHours"] == 24
    assert anticipation.reconcile(forecast, datetime.now(timezone.utc).isoformat(), 0.2, 0.1)["result"] == "hit"


def test_alert_lifecycle_and_incident(store, scope):
    plan = store.get_plan(scope.id)
    finding = {"observed": 0.2, "baseline": {"mean": 0.03, "threshold": 0.08, "sigma": 2.5, "minChange": 0.06}, "trend": "increasing", "abruptness": 2.0, "temporalConfirmation": True, "fusion": {"confidence": 0.9, "method": "optical+sar"}, "suppression": 0.9, "confidence": 0.9}
    alert = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood", "lon": 7.1, "lat": 50.5, "valueEur": 5_000_000, "population": 800}, model_version="m1")
    assert alert.severity == "red"
    assert alert.urgency > 0.5
    assert alert_ops.find_duplicate(store, alert) is None
    store.save_alert(alert)
    duplicate = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood", "lon": 7.101, "lat": 50.501}, model_version="m1")
    assert alert_ops.find_duplicate(store, duplicate).id == alert.id
    incident = alert_ops.group_into_incident(store, alert)
    assert alert.incident_id == incident.id
    assert alert_ops.route_alert(alert)["assignee"]
    ack = alert_ops.transition(store, alert.id, "acknowledge", actor="a")
    assert ack.status == "acknowledged"
    assigned = alert_ops.transition(store, alert.id, "assign", actor="a", assignee="M. Keller")
    assert assigned.status == "assigned"
    assert alert_ops.sla_status(assigned)["breached"] is False
    assert alert_ops.why_panel(finding, scope, {})["human"].startswith("An analyst")
    assert alert_ops.handoff_payload(assigned, "claim")["draftOnly"] is True
    alert_ops.transition(store, alert.id, "investigate", actor="a")
    with pytest.raises(ValueError):
        alert_ops.transition(store, alert.id, "acknowledge")
    dismissed = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood", "lon": 7.2, "lat": 50.4}, model_version="m1")
    store.save_alert(dismissed)
    alert_ops.transition(store, dismissed.id, "dismiss", reason="false_positive")
    assert store.get_alert(dismissed.id).dismissed_reason == "false_positive"


def test_bulk_and_fatigue(store, scope):
    plan = store.get_plan(scope.id)
    finding = {"observed": 0.2, "baseline": {"mean": 0.03, "threshold": 0.08, "sigma": 2.5, "minChange": 0.06}, "trend": "increasing", "abruptness": 2.0, "temporalConfirmation": True, "fusion": {"confidence": 0.9}, "suppression": 0.9, "confidence": 0.9}
    ids = []
    for i in range(3):
        alert = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood", "lon": 7.0 + i / 100, "lat": 50.4}, model_version="m1")
        store.save_alert(alert)
        ids.append(alert.id)
    result = alert_ops.bulk_action(store, ids, "acknowledge")
    assert len(result["done"]) == 3
    assert alert_ops.fatigue_budget(store, "tenant-a")["alerts"] == 3
    assert alert_ops.digest(store, "tenant-a")["alerts"] == 3
    assert alert_ops.dismissal_reasons()["false_positive"]
    assert alert_ops.customer_status_update(store.get_alert(ids[0]), author="A", message="m")["generated"] is False


def test_notifications(store, scope):
    plan = store.get_plan(scope.id)
    finding = {"observed": 0.2, "baseline": {"mean": 0.03, "threshold": 0.08, "sigma": 2.5, "minChange": 0.06}, "trend": "increasing", "abruptness": 2.0, "temporalConfirmation": True, "fusion": {"confidence": 0.9}, "suppression": 0.9, "confidence": 0.9}
    alert = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood", "lon": 7.1, "lat": 50.5}, model_version="m1")
    store.save_alert(alert)
    prefs = TenantPreferences(tenant="tenant-a", channels=["email", "slack"], quiet_hours=None)
    store.save_preferences(prefs)
    service = notifications.NotificationService(store)
    queued = service.enqueue(alert, prefs)
    assert len(queued) >= 2
    delivered = service.deliver_due()
    assert delivered["sent"]
    assert service.outbox("tenant-a")
    assert notifications.sign_payload({"a": 1}, "secret") == notifications.sign_payload({"a": 1}, "secret")
    assert notifications.slack_blocks(alert, "link")["blocks"]
    assert notifications.teams_card(alert, "link")["type"] == "AdaptiveCard"


def test_quiet_hours_and_red_override(store, scope):
    prefs = TenantPreferences(tenant="tenant-a", quiet_hours=(0, 23))
    moment = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    plan = store.get_plan(scope.id)
    finding = {"observed": 0.2, "baseline": {"mean": 0.03, "threshold": 0.08, "sigma": 2.5, "minChange": 0.06}, "trend": "increasing", "abruptness": 2.0, "temporalConfirmation": True, "fusion": {"confidence": 0.9}, "suppression": 0.9, "confidence": 0.9}
    yellow = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding={**finding, "confidence": 0.5}, plan=plan, observation={"changeType": "flood"}, model_version="m1")
    red = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood"}, model_version="m1")
    assert notifications.should_send(yellow, prefs, moment)[0] is False
    assert notifications.should_send(red, prefs, moment)[0] is True


def test_integrations(store, scope):
    plan = store.get_plan(scope.id)
    finding = {"observed": 0.2, "baseline": {"mean": 0.03, "threshold": 0.08, "sigma": 2.5, "minChange": 0.06}, "trend": "increasing", "abruptness": 2.0, "temporalConfirmation": True, "fusion": {"confidence": 0.9}, "suppression": 0.9, "confidence": 0.9}
    alert = alert_ops.make_alert(tenant="tenant-a", scope=scope, finding=finding, plan=plan, observation={"changeType": "flood"}, model_version="m1")
    assert dispatch_system("jira", alert)["dryRun"] is True
    assert dispatch_system("maximo", alert)["payload"]["workOrder"]["humanApprovalRequired"] is True
    assert integrations.arcgis_feature_layer("t", [alert], [scope])["features"]
    assert "<qgis" in integrations.qgis_monitoring_project("t", [scope], [alert])
    assert integrations.siem_event(alert)["humanReviewRequired"] is True


def test_governance(store, scope, tmp_path):
    registry = ModelRegistry(store)
    registry.register("model", "1.0", metrics={"precision": 0.8})
    registry.deploy("model", "1.1", metrics={"precision": 0.9})
    assert registry.deployed("model").version == "1.1"
    assert registry.rollback("model").version == "1.0"
    keyring = TenantKeyring(tmp_path)
    token, key_id = keyring.encrypt("tenant-a", "secret")
    assert keyring.decrypt("tenant-a", token) == "secret"
    assert key_id
    kill = KillSwitch(store)
    assert kill.set("tenant-a", True)["active"] is True
    assert kill.active("tenant-a") is True
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("k") and limiter.allow("k") and not limiter.allow("k")
    assert OnCallSchedule().current()["primary"]
    assert privacy_review_proactive()["items"]
    assert retention_policy(store, "tenant-a", days=1)["cutoff"]
    assert alert_quality(store, "tenant-a")["precision"] == 0
    with pytest.raises(NonGoalError):
        enforce_non_goal("automated-claim-approval")


def test_validation_gate(store, scope):
    plan = store.get_plan(scope.id)
    plan.first_n_alerts_require_analyst = 2
    store.save_plan(plan)
    gate = ValidationGate(store)
    assert gate.can_notify(scope.id, plan, Alert(
        id="A", tenant="tenant-a", scope_id=scope.id, title="t", summary="s", severity="red",
        urgency=0, confidence=0.9, change_type="flood", observed=0.2, baseline=0.03, lon=7, lat=50,
    ))[0] is False
    gate.record(scope.id, "A", "analyst", "validated")
    gate.record(scope.id, "A", "analyst", "validated")
    assert gate.can_notify(scope.id, plan, Alert(
        id="A", tenant="tenant-a", scope_id=scope.id, title="t", summary="s", severity="red",
        urgency=0, confidence=0.9, change_type="flood", observed=0.2, baseline=0.03, lon=7, lat=50,
    ))[0] is True


def test_engine_ingest_and_tick(store, scope):
    plan = store.get_plan(scope.id)
    plan.first_n_alerts_require_analyst = 0
    store.save_plan(plan)
    engine = ProactiveEngine(store)
    first = engine.ingest(scope.id, {"changeFraction": 0.12, "confidence": 0.8, "cloud": 0.02, "changeType": "flood", "sarConfidence": 0.7, "sar": True})
    second = engine.ingest(scope.id, {"changeFraction": 0.2, "confidence": 0.92, "cloud": 0.02, "changeType": "flood", "sarConfidence": 0.85, "sar": True})
    assert second["status"] in {"alert", "duplicate"}
    tick = engine.run_tick(tenant="tenant-a")
    assert "quality" in tick
    dashboard = engine.dashboard("tenant-a")
    assert dashboard["scopes"] == 1
    assert engine.pilot_report("tenant-a")["gates"]
    alert_id = second["alert"]["id"]
    assert engine.explain(alert_id)["alertId"] == alert_id
    assert engine.handoff(alert_id, "assessment")["humanReviewRequired"] is True


def test_demo_payload():
    data = build_demo()
    assert len(data["scopes"]) == 6
    assert len(data["alerts"]) >= 20
    assert data["dashboard"]["alerts"] == len(data["alerts"])
    assert data["watch"]["watchlist"]
    assert data["pilot"]["gates"]["precision"] is True
    assert data["digest"]["alerts"] >= 1
    assert data["governance"]["models"]
    assert data["calendar"]
    assert data["coverage"]


def test_api_proactive():
    from fastapi.testclient import TestClient

    from georesponse.api import app

    client = TestClient(app)
    overview = client.get("/api/watch/overview")
    assert overview.status_code == 200
    assert overview.json()["scopes"]
    scopes = client.get("/api/watch/scopes")
    assert scopes.status_code == 200
    alert_id = overview.json()["alerts"][0]["id"]
    assert client.get(f"/api/watch/alerts/{alert_id}").status_code == 200
    assert client.get("/api/watch/dashboard").status_code == 200
    assert client.get("/api/watch/pilot").status_code == 200
    assert client.get("/api/watch/digest").status_code == 200
    assert client.get("/api/watch/coverage").status_code == 200
    assert client.get("/api/watch/forecasts").status_code == 200
    assert client.get("/api/watch/preferences").status_code == 200
    assert client.post("/api/watch/tick").status_code == 200
