"""Adapter parity and approval tests for the LAIX geospatial pack."""

from __future__ import annotations

import json

import pytest

from georesponse.laix_adapter import (
    DecisionEngineFacade,
    OutcomeLoop,
    estimate,
    reset_facades,
)
from georesponse.proactive.engine import ProactiveEngine
from georesponse.proactive.models import (
    Alert,
    Baseline,
    MonitoringPlan,
    Scope,
    add_hours,
    new_id,
    utcnow,
)
from georesponse.proactive.store import ProactiveStore


@pytest.fixture()
def store():
    db = ProactiveStore(":memory:")
    yield db
    db.close()
    reset_facades()


@pytest.fixture()
def scope(store):
    item = Scope(
        id="scope-ahr",
        tenant="demo",
        name="Ahr supply corridor",
        kind="corridor",
        region="Ahr",
        center=(7.1, 50.545),
        bbox=(7.03, 50.51, 7.18, 50.57),
        asset_class="utility",
        change_types=["flood"],
        cadence="daily",
    )
    store.save_scope(item)
    store.save_plan(MonitoringPlan(scope_id=item.id, cadence="daily", sla_hours=4, budget_eur_per_month=2500))
    return item


def make_alert(store: ProactiveStore, scope: Scope, *, severity="red", confidence=0.92, urgency=0.91,
               sla_hours=4, status="new") -> Alert:
    alert = Alert(
        id=new_id("ALT"),
        tenant=scope.tenant,
        scope_id=scope.id,
        title="Flood change",
        summary="Flood edge reached the care campus",
        severity=severity,
        urgency=urgency,
        confidence=confidence,
        change_type="flood",
        observed=0.4,
        baseline=0.02,
        lon=7.1,
        lat=50.545,
        status=status,
        sla_due=add_hours(utcnow(), sla_hours),
        asset="Corridor",
        value_eur=12_000_000,
        population=1800,
        access="flooded",
        source="sentinel-2",
        model_version="test",
    )
    store.save_alert(alert)
    return alert


CASES = [
    ("red", 0.92, 0.91, 4, "act"),
    ("orange", 0.75, 0.62, 4, "guide"),
    ("yellow", 0.70, 0.35, 4, "wait"),
    ("red", 0.40, 0.95, 4, "ask"),
    ("red", 0.92, 0.95, -1, "escalate"),
]


@pytest.mark.parametrize("severity,confidence,urgency,sla_hours,verb", CASES)
def test_native_and_laix_agree(store, scope, severity, confidence, urgency, sla_hours, verb):
    alert = make_alert(store, scope, severity=severity, confidence=confidence, urgency=urgency, sla_hours=sla_hours)
    result = DecisionEngineFacade(store, mode="shadow").triage(alert)
    assert result["native"]["verb"] == verb
    assert result["laix"]["verb"] == verb
    assert result["parity"]["agrees"] is True
    assert result["decision"]["rationale"]


def test_shadow_keeps_native_authoritative_and_records_parity(store, scope):
    facade = DecisionEngineFacade(store, mode="shadow")
    alert = make_alert(store, scope)
    result = facade.triage(alert)
    assert result["authoritativeSource"] == "native"
    parity = json.loads(store.meta_get("laix:parity:demo"))
    assert parity["samples"] == 1
    assert parity["agreements"] == 1
    assert parity["agreementRate"] == 1.0


def test_laix_mode_is_authoritative(store, scope):
    facade = DecisionEngineFacade(store, mode="laix")
    alert = make_alert(store, scope)
    result = facade.triage(alert)
    assert result["authoritativeSource"] == "laix"
    assert result["authoritative"]["verb"] == "act"
    assert result["decision"]["policy_version"] == facade.runtime.policy.version


def test_evaluate_all_is_side_effect_free(store, scope):
    facade = DecisionEngineFacade(store, mode="shadow")
    make_alert(store, scope)
    make_alert(store, scope, severity="orange", confidence=0.75, urgency=0.62)
    before = facade.status("demo")["parity"]["samples"]
    report = facade.evaluate_all("demo")
    after = facade.status("demo")["parity"]["samples"]
    assert report["samples"] == 2
    assert report["agreementRate"] == 1.0
    assert before == after


def test_engine_reports_decision_on_ingest(store, scope, monkeypatch):
    from georesponse.laix_adapter import reset_facades

    monkeypatch.delenv("GEORESPONSE_DECISION_ENGINE", raising=False)
    reset_facades()
    store.save_baseline(Baseline(scope_id=scope.id, metric="change_fraction", values=[0.019, 0.021, 0.018, 0.02, 0.017] * 2).recompute())
    engine = ProactiveEngine(store)
    base = {
        "metric": "change_fraction",
        "confidence": 0.92,
        "optical": True,
        "sar": True,
        "sarConfidence": 0.86,
        "cloud": 0.03,
        "season": "summer",
        "changeType": "flood",
        "lon": 7.1,
        "lat": 50.545,
        "summary": "Flood edge reached the site",
        "asset": "Corridor",
        "valueEur": 12_000_000,
        "population": 1800,
        "access": "flooded",
    }
    engine.ingest(scope.id, {**base, "changeFraction": 0.34})
    result = engine.ingest(scope.id, {**base, "changeFraction": 0.40})
    assert result["status"] == "alert"
    assert result["decision"]["mode"] == "native"
    assert result["alert"]["status"] == "new"


def test_laix_flag_makes_engine_authoritative(store, scope, monkeypatch):
    from georesponse.laix_adapter import reset_facades

    monkeypatch.setenv("GEORESPONSE_DECISION_ENGINE", "laix")
    reset_facades()
    engine = ProactiveEngine(store)
    assert engine.decisions.mode == "laix"
    store.save_baseline(Baseline(scope_id=scope.id, metric="change_fraction", values=[0.019, 0.021, 0.018, 0.02, 0.017] * 2).recompute())
    base = {
        "metric": "change_fraction",
        "confidence": 0.92,
        "optical": True,
        "sar": True,
        "cloud": 0.03,
        "changeType": "flood",
        "lon": 7.1,
        "lat": 50.545,
        "summary": "Flood edge reached the site",
        "valueEur": 12_000_000,
        "population": 1800,
        "access": "flooded",
    }
    engine.ingest(scope.id, {**base, "changeFraction": 0.34})
    result = engine.ingest(scope.id, {**base, "changeFraction": 0.40})
    assert result["decision"]["mode"] == "laix"
    assert result["decision"]["authoritativeSource"] == "laix"


def test_approval_bridge_creates_and_approves_a_proposal(store, scope):
    facade = DecisionEngineFacade(store, mode="laix")
    alert = make_alert(store, scope)
    result = facade.triage(alert)
    decision_id = result["decision"]["id"]
    action = facade.runtime.action_for(facade.runtime.decision(decision_id))
    assert action is not None
    proposed = facade.propose(facade.runtime.decision(decision_id), action, alert_id=alert.id)
    assert proposed["proposal"]["status"] == "pending"
    assert proposed["proposal"]["action"] == "assign"

    approved = facade.approvals.proposals.approve(proposed["proposal"]["id"], actor="M. Keller")
    assert approved["status"] == "approved"
    updated = store.get_alert(alert.id)
    assert updated.status == "assigned"
    assert updated.assignee == action.params["assignee"]


def test_outcome_loop_attributes_acknowledgement_speed(store, scope):
    facade = DecisionEngineFacade(store, mode="laix")
    alert = make_alert(store, scope)
    result = facade.triage(alert)
    decision = facade.runtime.decision(result["decision"]["id"])
    action = facade.runtime.action_for(decision)
    assert action is not None
    receipt = facade.execute(decision, actor="M. Keller", approver="M. Keller")
    assert receipt["status"] == "executed"
    refreshed = store.get_alert(alert.id)
    outcome = OutcomeLoop(facade.runtime).acknowledge_speed(decision.id, refreshed, expected_minutes=240)
    assert outcome is not None
    assert outcome.label == "helped"
    assert outcome.attributed is True
    assert outcome.direction == "lower-better"


def test_sensing_budget_skips_commercial_when_budget_is_small(store, scope):
    plan = MonitoringPlan(scope_id=scope.id, sources=["sentinel-2", "planet"], budget_eur_per_month=100)
    result = estimate(plan, uncertainty=0.9)
    assert "coverage-check" in result["allowed"]
    assert "acquire:sentinel-2" in result["allowed"]
    assert "acquire:planet" not in result["allowed"]
    assert any("cost budget" in item["reason"] for item in result["skipped"])


def test_sensing_budget_allows_commercial_within_budget(store, scope):
    plan = MonitoringPlan(scope_id=scope.id, sources=["sentinel-2", "planet"], budget_eur_per_month=2500)
    result = estimate(plan, uncertainty=0.9)
    assert "acquire:planet" in result["allowed"]
    assert result["estimatedCostEur"] >= 450
