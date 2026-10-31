"""Translate a GeoResponse alert into a LAIX situation and its options.

This is the only place that knows about scopes, alerts, SLAs and imagery
sources.  ``laix`` itself stays domain-neutral.
"""

from __future__ import annotations

import math
from typing import Iterable

from laix import (
    Action,
    Belief,
    Constraint,
    Goal,
    Observation,
    Situation,
    iso,
    parse_iso,
)

from ..proactive import alerts as alert_ops
from ..proactive.models import Alert, MonitoringPlan

# The three analysts used by the demo routing table.  A real deployment passes
# the on-call rota instead; the adapter never invents people beyond this default.
DEFAULT_ANALYSTS = ("A. Weber", "M. Keller", "S. Okafor")


def _value_priority(alert: Alert) -> float:
    value = max(1.0, float(alert.value_eur or 0))
    population = max(1.0, float(alert.population or 0))
    return round(min(1.0, 0.6 * (math.log10(value) / 8.0) + 0.4 * (math.log10(population) / 5.0)), 4)


def situation_from_alert(
    alert: Alert,
    *,
    plan: MonitoringPlan | None = None,
    analysts: Iterable[str] | None = None,
    now: str | None = None,
) -> Situation:
    """Build the situation the policy sees.

    Severity, urgency and SLA remain the app's own measures.  LAIX consumes
    them as attributes; it does not re-derive the geospatial score.
    """
    moment = now or iso()
    plan = plan or MonitoringPlan(scope_id=alert.scope_id)
    sla = alert_ops.sla_status(alert, parse_iso(moment))
    deadline = parse_iso(alert.sla_due)
    phase = "decide"
    if alert.status in {"assigned", "investigating"}:
        phase = "verify"
    elif alert.status in {"resolved", "dismissed"}:
        phase = "adapt"

    observation = Observation(
        id=f"obs-{alert.id}",
        at=moment,
        source=alert.source or "unknown",
        kind="measurement",
        confidence=alert.confidence,
        payload={
            "alert": alert.id,
            "scope": alert.scope_id,
            "change_type": alert.change_type,
            "observed": alert.observed,
            "baseline": alert.baseline,
            "severity": alert.severity,
            "value_eur": alert.value_eur,
            "population": alert.population,
            "access": alert.access,
            "proposition": "change_confirmed",
            "statement": alert.summary,
            "expires_at": alert.sla_due,
            "confidence": alert.confidence,
        },
    )
    belief = Belief(
        id="change_confirmed",
        proposition=f"{alert.change_type} change is confirmed in {alert.scope_id}",
        confidence=alert.confidence,
        evidence=(observation.id,),
        updated_at=moment,
        expires_at=alert.sla_due,
        source=alert.model_version or alert.source,
    )
    goals = (
        Goal(
            id="g-decide-in-time",
            statement="decide before the SLA clock expires",
            priority=0.95 if alert.severity == "red" else 0.6,
            metric="time_to_decision_minutes",
            target=float(plan.sla_hours) * 60.0,
            deadline=alert.sla_due,
        ),
        Goal(
            id="g-protect-value",
            statement="protect the asset and the people exposed",
            priority=_value_priority(alert),
            metric="value_eur",
            target=float(alert.value_eur or 0),
        ),
        Goal(
            id="g-limit-interruptions",
            statement="do not wake an analyst without evidence",
            priority=0.25,
            metric="interruptions",
        ),
    )
    constraints = (
        Constraint(id="c-sla", kind="policy", value=plan.sla_hours, hard=False, statement="SLA window in hours"),
        Constraint(id="c-approval", kind="approval", value="required", hard=True, statement="a human approves every write"),
        Constraint(id="c-interrupt", kind="interruption", value=0.9, hard=False, statement="prefer low-interruption actions"),
        Constraint(id="c-risk", kind="risk", value=0.9, hard=True, statement="never take an action above 90% risk"),
        Constraint(id="c-budget", kind="budget", value=max(1.0, float(plan.budget_eur_per_month)), hard=False, statement="monthly sensing budget"),
    )
    uncertain = round(max(0.0, 1.0 - alert.confidence), 4)
    return Situation(
        id=f"sit-{alert.id}",
        at=moment,
        subject=alert.scope_id,
        observations=(observation,),
        beliefs=(belief,),
        goals=goals,
        constraints=constraints,
        phase=phase,
        horizon="hours",
        attributes={
            "urgency": round(float(alert.urgency), 4),
            "confidence": round(float(alert.confidence), 4),
            "uncertainty": uncertain,
            "severity": alert.severity,
            "change_type": alert.change_type,
            "sla_breached": bool(sla["breached"]),
            "sla_minutes_remaining": sla["minutesRemaining"],
            "sla_due": alert.sla_due,
            "deadline": iso(deadline) if deadline else None,
            "verification_due": alert.status in {"assigned", "investigating"} and not alert.acknowledged_at,
            "analysts": list(analysts or DEFAULT_ANALYSTS),
        },
    )


def options_for_alert(
    alert: Alert,
    *,
    plan: MonitoringPlan | None = None,
    analysts: Iterable[str] | None = None,
) -> tuple[Action, ...]:
    """The six verbs as concrete GeoResponse affordances.

    Assignment is reversible, but still requires a human approval because the
    product rule is stronger than LAIX's default: no one is dispatched by a
    machine.  The proposal registry is the approval gate.
    """
    plan = plan or MonitoringPlan(scope_id=alert.scope_id)
    route = alert_ops.route_alert(alert, rules=plan.escalation, analysts=list(analysts or DEFAULT_ANALYSTS))
    params = {
        "alert_id": alert.id,
        "scope_id": alert.scope_id,
        "tenant": alert.tenant,
        "team": route.get("team"),
        "assignee": route.get("assignee"),
        "severity": alert.severity,
        "sla_due": alert.sla_due,
    }
    return (
        Action(
            id=f"opt-wait-{alert.id}",
            verb="wait",
            name="observe_alert",
            expected_benefit=0.20,
            cost=0.0,
            risk=0.0,
            interrupt_cost=0.0,
            params=dict(params),
            rationale="keep watching; no analyst is disturbed",
        ),
        Action(
            id=f"opt-ask-{alert.id}",
            verb="ask",
            name="request_better_evidence",
            expected_benefit=0.55,
            cost=0.2,
            risk=0.05,
            latency_ms=600_000,
            interrupt_cost=0.20,
            reversible=True,
            params=dict(params),
            rationale="ask for a clearer view, a radar pass or an analyst label",
        ),
        Action(
            id=f"opt-guide-{alert.id}",
            verb="guide",
            name="show_ranked_shortlist",
            expected_benefit=0.66,
            cost=0.0,
            risk=0.05,
            interrupt_cost=0.30,
            reversible=True,
            params=dict(params),
            rationale="put the alert and its evidence in front of the analyst",
        ),
        Action(
            id=f"opt-act-{alert.id}",
            verb="act",
            name="assign_alert",
            expected_benefit=0.92,
            cost=0.0,
            risk=0.10,
            interrupt_cost=0.65,
            destructive=False,
            reversible=True,
            requires_approval=True,
            params=dict(params),
            rationale="assign an owner to the alert; a human must approve it",
        ),
        Action(
            id=f"opt-verify-{alert.id}",
            verb="verify",
            name="verify_alert_outcome",
            expected_benefit=0.50,
            cost=0.0,
            risk=0.0,
            latency_ms=5_000,
            interrupt_cost=0.25,
            reversible=True,
            params=dict(params),
            rationale="check whether the analyst action and SLA outcome held",
        ),
        Action(
            id=f"opt-escalate-{alert.id}",
            verb="escalate",
            name="escalate_sla",
            expected_benefit=0.98,
            cost=0.0,
            risk=0.20,
            interrupt_cost=0.95,
            reversible=True,
            params=dict(params),
            rationale="the SLA is breached; raise it to the on-call lead",
        ),
    )


def triage_inputs(
    alert: Alert,
    *,
    plan: MonitoringPlan | None = None,
    analysts: Iterable[str] | None = None,
    now: str | None = None,
) -> tuple[Situation, tuple[Action, ...]]:
    situation = situation_from_alert(alert, plan=plan, analysts=analysts, now=now)
    return situation, options_for_alert(alert, plan=plan, analysts=analysts)


def native_verb(alert: Alert, *, plan: MonitoringPlan | None = None) -> str:
    """The pre-LAIX triage rule, kept as the parity baseline.

    It deliberately uses only measures GeoResponse already had: SLA state,
    severity, confidence and the existing urgency score.
    """
    plan = plan or MonitoringPlan(scope_id=alert.scope_id)
    sla = alert_ops.sla_status(alert)
    if sla["breached"]:
        return "escalate"
    if alert.confidence <= 0.55:
        return "ask"
    if alert.status in {"assigned", "investigating"} and not alert.acknowledged_at:
        return "verify"
    if alert.urgency >= 0.75 and alert.confidence >= 0.80:
        return "act"
    if alert.urgency >= 0.45:
        return "guide"
    return "wait"


def native_triage(
    alert: Alert,
    *,
    plan: MonitoringPlan | None = None,
    analysts: Iterable[str] | None = None,
) -> dict:
    plan = plan or MonitoringPlan(scope_id=alert.scope_id)
    route = alert_ops.route_alert(alert, rules=plan.escalation, analysts=list(analysts or DEFAULT_ANALYSTS))
    sla = alert_ops.sla_status(alert)
    verb = native_verb(alert, plan=plan)
    return {
        "source": "native",
        "verb": verb,
        "assignee": route.get("assignee") if verb in {"act", "escalate"} else None,
        "team": route.get("team") if verb in {"act", "escalate"} else None,
        "routing": route.get("via"),
        "severity": alert.severity,
        "urgency": round(float(alert.urgency), 4),
        "confidence": round(float(alert.confidence), 4),
        "requiresApproval": verb == "act",
        "slaBreached": bool(sla["breached"]),
    }


def laix_view(
    decision,
    *,
    action: Action | None,
    alert: Alert,
) -> dict:
    params = dict(action.params) if action else {}
    owns = decision.verb in {"act", "escalate"}
    return {
        "source": "laix",
        "verb": decision.verb,
        "action": decision.action_id,
        "actionName": action.name if action else None,
        "assignee": params.get("assignee") if owns else None,
        "team": params.get("team") if owns else None,
        "severity": alert.severity,
        "urgency": decision.attributes.get("urgency", round(float(alert.urgency), 4)),
        "confidence": round(float(decision.confidence), 4),
        "requiresApproval": decision.requires_approval,
        "rationale": decision.rationale,
        "policyVersion": decision.policy_version,
        "traceId": decision.trace_id,
    }


def compare(native: dict, laix_decision: dict) -> dict:
    differences = []
    if native["verb"] != laix_decision["verb"]:
        differences.append({"field": "verb", "native": native["verb"], "laix": laix_decision["verb"]})
    if native["verb"] == "act" and laix_decision["verb"] == "act" and native["assignee"] != laix_decision["assignee"]:
        differences.append({"field": "assignee", "native": native["assignee"], "laix": laix_decision["assignee"]})
    return {"agrees": not differences, "differences": differences}
