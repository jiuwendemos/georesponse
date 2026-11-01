"""One-path LAIX adapter tests.

GeoResponse calls LAIX for every alert decision. There is no native, shadow or
parity runtime to compare against; the captured fixture is the only historical
comparison and it records the real differences.
"""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import laix
from georesponse.api import app
from georesponse.laix_adapter import (
    DecisionEngineFacade,
    OutcomeLoop,
    estimate,
    options_for_alert,
    situation_from_alert,
)
from georesponse.laix_adapter import facade as facade_module
from georesponse.proactive.models import (
    Alert,
    MonitoringPlan,
    Scope,
    add_hours,
    new_id,
    utcnow,
)
from georesponse.proactive.store import ProactiveStore

from laix import Action, Belief, Constraint, DecisionRequest, Goal, Layer, Observation, Situation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "laix_parity_demo.json"
client = TestClient(app)


@pytest.fixture()
def store():
    db = ProactiveStore(":memory:")
    yield db
    db.close()


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


# --------------------------------------------------------------------- mapping


def test_alert_maps_to_a_lai_situation(store, scope):
    alert = make_alert(store, scope, status="assigned", sla_hours=-1)
    situation = situation_from_alert(alert)
    assert situation.subject == scope.id
    assert situation.beliefs[0].confidence == alert.confidence
    assert situation.attributes["urgency"] == alert.urgency
    assert situation.attributes["deadline_breached"] is True
    assert situation.attributes["verification_due"] is True
    assert "sla_breached" not in situation.attributes
    assert any(item.kind == "approval" for item in situation.constraints)
    assert situation.observations[0].payload["alert"] == alert.id


def test_alert_maps_to_lai_action_options(store, scope):
    alert = make_alert(store, scope)
    options = options_for_alert(alert, analysts=["Only Analyst"])
    assert {item.verb for item in options} == {"wait", "ask", "guide", "act", "verify", "escalate"}
    act = next(item for item in options if item.verb == "act")
    assert act.name == "assign_alert"
    assert act.requires_approval is True
    assert act.params["alert_id"] == alert.id
    assert act.params["assignee"] == "Only Analyst"


def test_decision_maps_back_to_a_georesponse_view(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    view = result["laix"]
    assert result["engine"] == "laix"
    assert view["verb"] in {"wait", "observe", "ask", "guide", "act", "verify", "escalate"}
    assert view["action"] == result["decision"]["action_id"]
    assert view["confidence"] == result["decision"]["confidence"]
    assert view["policyVersion"] == facade.layer.runtime.policy.version
    assert view["reasonCode"]
    assert "constraintsApplied" not in view
    assert any(event["action"] == "laix.decision" for event in store.audit_events("demo"))


def test_status_reports_lai_versions_and_no_mode(store):
    facade = DecisionEngineFacade(store)
    status = facade.status()
    assert status["engine"] == "laix"
    assert status["package"] == "laix"
    assert status["policyVersion"] == facade.layer.status()["policyVersion"]
    assert status["schemaVersion"] == laix.SCHEMA_VERSION
    assert not {"mode", "modes", "parity", "flag"}.intersection(status)


# ----------------------------------------------------------------------- apply


@pytest.mark.parametrize("verb", ["wait", "observe", "ask", "guide"])
def test_non_action_verbs_clear_an_implied_owner(store, scope, verb):
    alert = make_alert(store, scope)
    alert.assignee = "A. Weber"
    facade = DecisionEngineFacade(store)
    facade.apply(alert, {"laix": {"verb": verb}})
    assert alert.assignee is None


def test_escalation_tags_the_alert(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    facade.apply(alert, {"laix": {"verb": "escalate"}})
    assert "sla-escalated" in alert.tags


# ------------------------------------------------------------- approval/execute


def test_approval_bridge_creates_and_approves_a_proposal(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    decision = facade.decision(result["decision"]["decision_id"])
    action = facade.action(result["decision"]["decision_id"])
    assert action is not None

    proposed = facade.propose(decision, action, alert_id=alert.id)
    assert proposed["proposal"]["status"] == "pending"
    assert proposed["proposal"]["action"] == "assign"

    approved = facade.approvals.proposals.approve(proposed["proposal"]["id"], actor="M. Keller")
    assert approved["status"] == "approved"
    updated = store.get_alert(alert.id)
    assert updated.status == "assigned"
    assert updated.assignee == action.params["assignee"]


def test_lai_executes_an_approved_action_and_returns_a_receipt(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    decision = facade.decision(result["decision"]["decision_id"])
    receipt = facade.execute(decision, actor="M. Keller", approver="M. Keller")
    assert receipt["status"] == "executed"
    updated = store.get_alert(alert.id)
    assert updated.status == "assigned"


def test_lai_execution_forwards_the_actor_context(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    decision = facade.decision(result["decision"]["decision_id"])
    received: dict[str, object] = {}

    def spy(action, context):
        received.update(context)
        return {"ok": True}

    facade.layer.bridge().register("assign_alert", spy)
    receipt = facade.execute(
        decision,
        actor="M. Keller",
        approver="M. Keller",
        context={"actor": "M. Keller"},
    )
    assert received["actor"] == "M. Keller"
    assert receipt["status"] == "executed"
    assert receipt["approved_by"] == "M. Keller"


def test_lai_approval_is_scoped_to_act():
    cases = (
        ("wait", {"urgency": 0.1, "confidence": 0.9}, ("wait",)),
        ("observe", {"urgency": 0.1, "confidence": 0.9, "uncertainty": 0.6}, ("observe",)),
        ("ask", {"urgency": 0.1, "confidence": 0.9, "uncertainty": 0.6}, ("ask",)),
        ("guide", {"urgency": 0.6, "confidence": 0.9}, ("guide",)),
        ("act", {"urgency": 0.9, "confidence": 0.9}, ("act",)),
        ("verify", {"urgency": 0.1, "confidence": 0.9, "verification_due": True}, ("verify",)),
        ("escalate", {"urgency": 0.1, "confidence": 0.9, "deadline_breached": True}, ("escalate",)),
    )
    for verb, attributes, option_verbs in cases:
        situation = Situation(
            id=f"sit-{verb}",
            at="2026-01-01T00:00:00+00:00",
            subject="approval-scope",
            beliefs=(Belief(id="b", proposition="the condition is real", confidence=0.9),),
            constraints=(Constraint(id="c-approval", kind="approval", value="required", hard=True),),
            attributes=dict(attributes),
        )
        options = tuple(
            Action(id=f"opt-{item}", verb=item, name=f"do-{item}", expected_benefit=0.9)
            for item in dict.fromkeys((*option_verbs, "wait"))
        )
        layer = Layer()
        decision = layer.decide(DecisionRequest(subject=verb, at=situation.at, situation=situation, options=options))[0]
        core = layer._core_decisions[decision.decision_id]
        assert decision.verb == verb
        assert decision.requires_approval is (verb == "act")
        assert ("approval:human-required" in core.constraints_applied) is (verb == "act")


# ---------------------------------------------------------------------- outcome


def test_outcome_attribution_uses_the_lai_receipt(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    decision = facade.decision(result["decision"]["decision_id"])
    facade.execute(decision, actor="M. Keller", approver="M. Keller")
    refreshed = store.get_alert(alert.id)
    outcome = OutcomeLoop(facade.layer).acknowledge_speed(decision, refreshed, expected_minutes=240)
    assert outcome is not None
    assert outcome.label == "helped"
    assert outcome.attributed is True
    assert outcome.direction == "lower-better"


def test_outcome_without_a_receipt_is_not_attributed(store, scope):
    alert = make_alert(store, scope)
    facade = DecisionEngineFacade(store)
    result = facade.triage(alert)
    decision = facade.decision(result["decision"]["decision_id"])
    refreshed = store.get_alert(alert.id)
    refreshed.acknowledged_at = add_hours(utcnow(), 0.05)
    outcome = OutcomeLoop(facade.layer).acknowledge_speed(decision, refreshed, expected_minutes=240)
    assert outcome is not None
    assert outcome.attributed is False


# ------------------------------------------------------------------- resources


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


# ------------------------------------------------------------------- isolation


def test_local_lai_package_is_gone_and_the_installed_package_is_used():
    assert not (ROOT / "laix").exists()
    installed = Path(laix.__file__).resolve()
    assert ROOT not in installed.parents
    assert version("laix") == "0.7.0"
    assert laix.SCHEMA_VERSION == "0.7.0"


def test_lai_pin_is_identical_and_tagged():
    pin = "laix @ git+https://github.com/michaelatamuk/laix.git@v0.7.0#subdirectory=packages/python/laix"
    assert pin in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert pin in (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "laix.git@main" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_old_mode_flag_and_parity_runtime_are_gone():
    for name in ("GEORESPONSE_DECISION_ENGINE", "MODES", "configured_mode", "ENV_FLAG", "PARITY_KEY"):
        assert not hasattr(facade_module, name)
    facade = DecisionEngineFacade(ProactiveStore(":memory:"))
    for name in ("mode", "parity", "reset_parity", "evaluate", "evaluate_all"):
        assert not hasattr(facade, name)


def test_parity_endpoints_are_gone_and_status_has_no_mode():
    assert client.get("/api/watch/decision-engine/evaluate").status_code in {404, 405}
    assert client.post("/api/watch/decision-engine/reset-parity").status_code in {404, 405}
    body = client.get("/api/watch/decision-engine").json()
    assert body["engine"] == "laix"
    assert body["policyVersion"]
    assert body["schemaVersion"]
    assert "mode" not in body
    assert "parity" not in body
    overview = client.get("/api/watch/overview").json()["decisionEngine"]
    assert "mode" not in overview
    assert "parity" not in overview


# ---------------------------------------------------------------------- parity


def _fixture_situation(payload: dict) -> Situation:
    return Situation(
        id=payload["id"],
        at=payload["at"],
        subject=payload["subject"],
        observations=tuple(Observation(**item) for item in payload["observations"]),
        beliefs=tuple(Belief(**item) for item in payload["beliefs"]),
        goals=tuple(Goal(**item) for item in payload["goals"]),
        constraints=tuple(Constraint(**item) for item in payload["constraints"]),
        phase=payload["phase"],
        horizon=payload["horizon"],
        attributes=dict(payload["attributes"]),
    )


def test_captured_parity_fixture_matches_real_lai():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["contract"] == "laix-georesponse-parity"
    assert len(fixture["cases"]) == 9

    exact = 0
    rationale_differences: list[dict] = []
    compared = 0
    for case in fixture["cases"]:
        situation = _fixture_situation(case["situation"])
        options = tuple(Action.from_dict(item) for item in case["options"])
        layer = Layer()
        layer.bridge().register("assign_owner", lambda action, context: {"ok": True})
        decision = layer.decide(
            DecisionRequest(subject=case["id"], at=situation.at, situation=situation, options=options)
        )[0]
        core = layer._core_decisions[decision.decision_id]
        actual = {
            "verb": decision.verb,
            "actionId": decision.action_id,
            "requiresApproval": decision.requires_approval,
            "rationale": decision.rationale,
            "confidence": round(decision.confidence, 6),
            "constraintsApplied": list(core.constraints_applied),
            "receiptStatus": None,
        }
        if decision.verb == "act":
            actual["receiptStatus"] = layer.execute(
                decision, actor="fixture-agent", approver="fixture-approver"
            ).status
        expected = case["laix"]
        for field in ("verb", "actionId", "requiresApproval", "confidence", "constraintsApplied", "receiptStatus"):
            compared += 1
            assert actual[field] == expected[field], (case["id"], field, actual[field], expected[field])
            exact += int(actual[field] == expected[field])
        compared += 1
        if actual["rationale"] == expected["rationale"]:
            exact += 1
        else:
            rationale_differences.append(
                {"case": case["id"], "captured": expected["rationale"], "actual": actual["rationale"]}
            )

    # LAIX 2026.2 uses exactly this wording.  The fixture is deliberately not
    # edited; the difference is asserted instead of hidden.
    assert len(rationale_differences) == 3
    for difference in rationale_differences:
        assert difference["captured"] == "a hard deadline or SLA is already breached"
        assert difference["actual"] == "a hard deadline or commitment is already breached"
    assert compared == 63
    assert exact == 60


def test_captured_native_baseline_and_laix_agree_on_approval():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    differences = [
        case
        for case in fixture["cases"]
        if case["native"]["requiresApproval"] != case["laix"]["requiresApproval"]
    ]
    assert differences == []
    assert all(case["laix"]["requiresApproval"] is (case["laix"]["verb"] == "act") for case in fixture["cases"])
