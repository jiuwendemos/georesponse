"""Golden replay tests for the portable LAIX package.

The fixture is captured from real GeoResponse triage decisions but contains only
portable LAIX contracts: no GeoResponse types, no generated IDs and no live
timestamps.  A policy or contract change must update the fixture deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path

import laix
from laix import Action, Belief, Constraint, DecisionRuntime, Goal, Observation, Situation

FIXTURE = Path(laix.__file__).resolve().parent / "fixtures" / "replay.json"
FIXED_AT = "2026-01-01T00:00:00+00:00"
EXPECTED_CASES = 10

HANDLERS = (
    "observe",
    "request_evidence",
    "show_shortlist",
    "assign_owner",
    "verify_outcome",
    "escalate_situation",
)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def to_situation(payload: dict) -> Situation:
    data = dict(payload)
    data["observations"] = tuple(Observation(**item) for item in payload.get("observations", []))
    data["beliefs"] = tuple(Belief(**item) for item in payload.get("beliefs", []))
    data["goals"] = tuple(Goal(**item) for item in payload.get("goals", []))
    data["constraints"] = tuple(Constraint(**item) for item in payload.get("constraints", []))
    return Situation(**data)


def to_options(payload: list[dict]) -> tuple[Action, ...]:
    return tuple(Action.from_dict(item) for item in payload)


def run_case(case: dict) -> list[dict]:
    situation = to_situation(case["situation"])
    options = to_options(case["options"])
    runtime = DecisionRuntime()
    for name in HANDLERS:
        runtime.bridge.register(name, lambda action, context: {"ok": True})

    decision = runtime.decide(situation, options)
    expected = case["expectedDecision"]
    diffs: list[dict] = []

    checks = {
        "verb": (decision.verb, expected["verb"]),
        "actionId": (decision.action_id, expected["actionId"]),
        "requiresApproval": (decision.requires_approval, expected["requiresApproval"]),
        "rationale": (decision.rationale, expected["rationale"]),
        "confidence": (round(decision.confidence, 6), expected["confidence"]),
        "constraintsApplied": (list(decision.constraints_applied), expected["constraintsApplied"]),
        "policyVersion": (decision.policy_version, expected["policyVersion"]),
    }
    for field, (actual, wanted) in checks.items():
        if actual != wanted:
            diffs.append({"case": case["id"], "field": field, "actual": actual, "expected": wanted})

    expected_receipt = case.get("expectedReceipt")
    if expected_receipt is not None:
        receipt = runtime.execute(decision, actor="fixture-agent", approver="fixture-approver")
        receipt_checks = {
            "receipt.status": (receipt.status, expected_receipt["status"]),
            "receipt.actionName": (receipt.action_name, expected_receipt["actionName"]),
            "receipt.approvedBy": (receipt.approved_by, expected_receipt["approvedBy"]),
            "receipt.detail": (receipt.detail, expected_receipt["detail"]),
        }
        for field, (actual, wanted) in receipt_checks.items():
            if actual != wanted:
                diffs.append({"case": case["id"], "field": field, "actual": actual, "expected": wanted})

    return diffs


def test_replay_fixture_shape() -> None:
    fixture = load_fixture()
    assert fixture["contract"] == "laix-replay"
    assert fixture["version"] == "1"
    assert fixture["capturedFrom"].startswith("georesponse@")
    assert len(fixture["cases"]) == EXPECTED_CASES
    ids = [case["id"] for case in fixture["cases"]]
    assert len(ids) == len(set(ids))
    assert "quickstart" in ids


def test_replay_fixture_has_no_live_timestamps_or_generated_ids() -> None:
    fixture = load_fixture()
    text = FIXTURE.read_text(encoding="utf-8")
    assert "ALT-" not in text
    assert "PROP-" not in text
    assert "scope-" not in text

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"at", "updated_at", "created_at"} and item is not None:
                    assert item == FIXED_AT, (key, item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(fixture)


def test_replay_matches_the_policy() -> None:
    diffs: list[dict] = []
    for case in load_fixture()["cases"]:
        diffs.extend(run_case(case))
    assert diffs == [], json.dumps(diffs[:10], indent=2)
