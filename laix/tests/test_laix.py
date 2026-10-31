"""Portable contract tests for the LAIX core.

These tests import only ``laix`` and the standard library.  They must keep
passing after the package is moved into another repository or vendored into a
different app.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import laix
from laix.contracts import (
    Action,
    Belief,
    Constraint,
    Decision,
    Goal,
    Observation,
    Situation,
    iso,
    utcnow,
)
from laix.execution import ApprovalRequired, ExecutionBridge
from laix.policy import DecisionPolicy, PolicyConfig, PolicyRequest
from laix.resources import Budget, ResourcePolicy, SensingOption
from laix.runtime import DecisionRuntime
from laix.schema import SCHEMA_PATH, build_schema, check, dumps_schema
from laix.state import ExperienceState


def situation(**attributes: object) -> Situation:
    return Situation(
        id="SIT-1",
        at=iso(),
        subject="demo",
        beliefs=(Belief(id="b-risk", proposition="risk is real", confidence=0.9),),
        goals=(Goal(id="g-1", statement="protect the asset", priority=0.9),),
        attributes=dict(attributes),
    )


def options(**overrides: object) -> tuple[Action, ...]:
    base = {
        "wait": Action(id="a-wait", verb="wait", name="observe", expected_benefit=0.2),
        "ask": Action(id="a-ask", verb="ask", name="request_evidence", expected_benefit=0.5),
        "guide": Action(id="a-guide", verb="guide", name="show_shortlist", expected_benefit=0.6),
        "act": Action(id="a-act", verb="act", name="assign_team", expected_benefit=0.9),
        "verify": Action(id="a-verify", verb="verify", name="check_outcome", expected_benefit=0.5),
        "escalate": Action(id="a-escalate", verb="escalate", name="breach_sla", expected_benefit=0.9),
    }
    base.update(overrides)
    return tuple(base.values())


# --------------------------------------------------------------------- package


def test_package_exposes_versioned_contracts() -> None:
    assert laix.SCHEMA_VERSION == "1.0"
    assert set(laix.CONTRACT_NAMES) == {
        "Observation",
        "Belief",
        "Goal",
        "Constraint",
        "Action",
        "Situation",
        "Decision",
        "Outcome",
        "Receipt",
        "Trace",
    }
    assert laix.VERBS == ("wait", "ask", "guide", "act", "verify", "escalate")


def test_core_imports_do_not_reference_the_host() -> None:
    root = Path(laix.__file__).resolve().parent
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "schema.py" or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "import georesponse" in text or "from georesponse" in text:
            offenders.append(path.name)
    assert offenders == []


# --------------------------------------------------------------------- schema


def test_committed_schema_is_current() -> None:
    assert SCHEMA_PATH.exists()
    assert SCHEMA_PATH.read_text(encoding="utf-8") == dumps_schema()


def test_schema_covers_every_contract() -> None:
    document = build_schema()
    assert set(document["$defs"]) == set(laix.CONTRACT_NAMES)
    assert document["version"] == laix.SCHEMA_VERSION


def test_schema_check_reports_missing_and_unknown_fields() -> None:
    assert check("Decision", {"id": "D"}) != []
    errors = check("Observation", {"id": "o", "at": "", "source": "s", "kind": "signal", "confidence": 0.5, "nope": 1})
    assert any("unknown field" in item for item in errors)
    good = Observation(id="o", at=iso(), source="s", kind="signal", confidence=0.5).to_dict()
    assert check("Observation", good) == []


# ---------------------------------------------------------------------- state


def test_state_merges_decays_and_expires_beliefs() -> None:
    state = ExperienceState(subject="demo")
    first = Observation(id="o1", at=iso(utcnow() - timedelta(hours=2)), source="a", kind="signal", confidence=0.8,
                        payload={"proposition": "risk", "confidence": 0.8})
    second = Observation(id="o2", at=iso(), source="b", kind="signal", confidence=0.9,
                         payload={"proposition": "risk", "confidence": 0.9})
    state.observe(first)
    state.observe(second)
    assert state.belief("risk") is not None
    assert 0.8 <= state.belief("risk").confidence <= 0.9
    state.decay(half_life_minutes=60)
    assert state.belief("risk").confidence < 0.9
    expired = Belief(id="old", proposition="old", confidence=0.5, expires_at=iso(utcnow() - timedelta(minutes=1)))
    state.set_belief(expired)
    assert state.expire() == ["old"]


def test_state_round_trips_through_snapshot() -> None:
    state = ExperienceState(subject="demo")
    state.observe(Observation(id="o", at=iso(), source="s", kind="signal", confidence=0.7,
                              payload={"proposition": "risk", "confidence": 0.7}))
    restored = ExperienceState.from_snapshot(state.snapshot())
    assert restored.subject == "demo"
    assert restored.belief("risk").confidence == state.belief("risk").confidence


# --------------------------------------------------------------------- policy


def test_policy_acts_when_urgency_and_confidence_are_high() -> None:
    request = PolicyRequest(situation(urgency=0.9), options())
    decision = DecisionPolicy().decide(request, decision_id="D1", trace_id="T1")
    assert decision.verb == "act"
    assert decision.action_id == "a-act"
    assert decision.requires_approval is False
    assert "act thresholds" in decision.rationale


def test_policy_asks_when_uncertain() -> None:
    weak = Situation(
        id="SIT-2", at=iso(), subject="demo",
        beliefs=(Belief(id="b", proposition="weak", confidence=0.3),),
        attributes={"urgency": 0.9},
    )
    decision = DecisionPolicy().decide(PolicyRequest(weak, options()))
    assert decision.verb == "ask"


def test_policy_escalates_before_acting_on_breach() -> None:
    decision = DecisionPolicy().decide(PolicyRequest(situation(urgency=0.99, sla_breached=True), options()))
    assert decision.verb == "escalate"


def test_policy_verifies_pending_outcome() -> None:
    decision = DecisionPolicy().decide(
        PolicyRequest(situation(urgency=0.99, verification_due=True), options())
    )
    assert decision.verb == "verify"


def test_policy_guides_a_mid_urgency_event() -> None:
    decision = DecisionPolicy().decide(PolicyRequest(situation(urgency=0.6), options()))
    assert decision.verb == "guide"


def test_policy_waits_when_nothing_clears_the_threshold() -> None:
    decision = DecisionPolicy().decide(PolicyRequest(situation(urgency=0.1), options()))
    assert decision.verb == "wait"


def test_policy_blocks_actions_that_break_hard_constraints() -> None:
    sit = situation(urgency=0.99)
    sit = Situation(
        id=sit.id, at=sit.at, subject=sit.subject, beliefs=sit.beliefs, goals=sit.goals,
        constraints=(Constraint(id="c-lat", kind="latency", value=100, hard=True),),
        attributes=sit.attributes,
    )
    slow = Action(id="a-slow", verb="act", name="slow_act", latency_ms=500, expected_benefit=0.99)
    decision = DecisionPolicy().decide(PolicyRequest(sit, (*options(), slow)))
    assert decision.action_id != "a-slow"
    assert any("latency" in item for item in decision.constraints_applied)
    assert any(item["action_id"] == "a-slow" for item in decision.alternatives)


def test_policy_requires_approval_for_destructive_actions() -> None:
    destructive = Action(id="a-delete", verb="act", name="delete", destructive=True, expected_benefit=0.99)
    decision = DecisionPolicy().decide(PolicyRequest(situation(urgency=0.99), (*options(), destructive)))
    assert decision.verb == "act"
    assert decision.requires_approval is True
    assert "approval:human-required" in decision.constraints_applied


def test_policy_safety_constraint_forces_wait() -> None:
    sit = Situation(
        id="S", at=iso(), subject="demo",
        constraints=(Constraint(id="safe", kind="safety", value="blocked", hard=True),),
        attributes={"urgency": 0.99},
    )
    decision = DecisionPolicy().decide(PolicyRequest(sit, options()))
    assert decision.verb == "wait"
    assert "safety" in decision.rationale


def test_policy_is_deterministic() -> None:
    request = PolicyRequest(situation(urgency=0.9), options())
    policy = DecisionPolicy()
    first = policy.decide(request, decision_id="D", trace_id="T", created_at="2026-01-01T00:00:00+00:00")
    second = policy.decide(request, decision_id="D", trace_id="T", created_at="2026-01-01T00:00:00+00:00")
    assert first.to_dict() == second.to_dict()


def test_policy_config_is_tunable() -> None:
    strict = DecisionPolicy(PolicyConfig(act_urgency=0.99, act_confidence=0.99))
    assert strict.decide(PolicyRequest(situation(urgency=0.9), options())).verb == "guide"


# -------------------------------------------------------------------- runtime


def test_runtime_records_trace_and_receipt() -> None:
    calls: list[dict] = []

    def assign(action: Action, context: dict) -> dict:
        calls.append({"name": action.name, "context": context})
        return {"assigned": True}

    bridge = ExecutionBridge(handlers={"assign_team": assign})
    runtime = DecisionRuntime(bridge=bridge)
    decision = runtime.decide(situation(urgency=0.9), options())
    receipt = runtime.execute(decision, actor="analyst")
    assert receipt.status == "executed"
    assert receipt.detail == {"assigned": True}
    assert calls and calls[0]["name"] == "assign_team"
    stages = [event["stage"] for event in runtime.trace(decision.id).events]
    assert stages[0] == "situation"
    assert "decided" in stages
    assert "execution.executed" in stages


def test_runtime_refuses_destructive_action_without_approval() -> None:
    destructive = Action(id="a-delete", verb="act", name="delete", destructive=True, expected_benefit=0.99)
    bridge = ExecutionBridge(handlers={"delete": lambda action, context: {"deleted": True}})
    runtime = DecisionRuntime(bridge=bridge)
    decision = runtime.decide(situation(urgency=0.99), (*options(), destructive))
    receipt = runtime.execute(decision, actor="agent")
    assert receipt.status == "refused"
    assert "approval" in (receipt.error or "")
    approved = runtime.execute(decision, actor="agent", approver="manager")
    assert approved.status == "executed"
    assert approved.approved_by == "manager"


def test_runtime_cancels_and_undoes() -> None:
    bridge = ExecutionBridge(
        handlers={"assign_team": lambda action, context: {"assigned": True}},
        undo_handlers={"assign_team": lambda action, context: {"unassigned": True}},
    )
    runtime = DecisionRuntime(bridge=bridge)
    decision = runtime.decide(situation(urgency=0.9), options())
    receipt = runtime.execute(decision, actor="analyst")
    undone = runtime.undo(receipt.id, actor="analyst")
    assert undone.status == "undone"
    assert undone.detail["undo"] == {"unassigned": True}

    pending = bridge._store(type(receipt)(id="RCT-X", decision_id=decision.id, action_name="assign_team", status="pending", actor="a"))
    cancelled = runtime.cancel(pending.id, actor="analyst", reason="situation changed")
    assert cancelled.status == "cancelled"


def test_runtime_measures_outcome() -> None:
    runtime = DecisionRuntime()
    decision = runtime.decide(situation(urgency=0.9), options())
    runtime.execute(decision, actor="analyst")
    outcome = runtime.measure(
        decision.id,
        metric="time_to_assessment",
        before=120.0,
        after=42.0,
        direction="lower-better",
        attributed=True,
    )
    assert outcome.label == "helped"
    summary = runtime.stats()["outcomes"]
    assert summary["attributed"] == 1
    assert summary["helped"] == 1


# ------------------------------------------------------------------ resources


def test_resource_policy_skips_deep_calls_when_uncertainty_is_low() -> None:
    policy = ResourcePolicy(min_information_gain=0.35)
    plan = policy.schedule(
        [
            SensingOption(name="cheap-diff", tier="cheap"),
            SensingOption(name="deep-model", tier="deep", cost=0.2, latency_ms=800, information_gain=0.5),
        ],
        budget=Budget(),
        uncertainty=0.2,
    )
    assert "cheap-diff" in plan.allowed
    assert "deep-model" not in plan.allowed
    assert plan.deep_calls == 0
    assert plan.skipped[0]["name"] == "deep-model"


def test_resource_policy_admits_deep_calls_within_budget() -> None:
    policy = ResourcePolicy()
    plan = policy.schedule(
        [SensingOption(name="deep", tier="deep", cost=0.3, latency_ms=500, information_gain=0.9)],
        budget=Budget(max_deep_calls=1, max_cost=1.0, max_latency_ms=1000),
        uncertainty=0.8,
    )
    assert plan.allowed == ("deep",)
    assert plan.deep_calls == 1


def test_resource_policy_enforces_latency_budget() -> None:
    plan = ResourcePolicy().schedule(
        [SensingOption(name="deep", tier="deep", latency_ms=5000, information_gain=0.99)],
        budget=Budget(max_latency_ms=1000),
        uncertainty=1.0,
    )
    assert plan.allowed == ()
    assert "latency" in plan.skipped[0]["reason"]
