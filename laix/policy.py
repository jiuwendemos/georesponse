"""Deterministic decision policy: rules first, learned policy later.

The policy never calls a model.  It reads a ``Situation`` plus the actions the
app can afford, removes options that violate hard constraints, and returns one
of six verbs with a written rationale and the rejected alternatives.

Rule order (first admissible match wins):

1. ``safety``   - a hard safety constraint blocks every action except wait
2. ``escalate`` - a hard deadline or SLA is already breached
3. ``ask``      - uncertainty is too high, or confidence is below the floor
4. ``verify``   - a previous action still has an unverified outcome
5. ``act``      - urgency and confidence both clear the act thresholds
6. ``guide``    - the situation is worth surfacing, but not acting on
7. ``wait``     - keep watching silently

Inside one verb band the highest utility wins; utility is deterministic and
never hidden in a model score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    VERBS,
    Action,
    Decision,
    Situation,
    clamp,
    iso,
)

POLICY_VERSION = "2026.1"


def _number(payload: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "required", "always", "blocked", "on"}
    return bool(value)


@dataclass(frozen=True)
class PolicyConfig:
    """Thresholds are explicit so a host can audit and tune them.

    The defaults reproduce a conservative analyst workflow: act only when both
    urgency and confidence are high, ask when the evidence is weak, and never
    interrupt for a low-urgency event.
    """

    min_confidence: float = 0.55
    act_confidence: float = 0.80
    ask_uncertainty: float = 0.45
    act_urgency: float = 0.75
    guide_urgency: float = 0.45
    max_risk: float = 0.90
    max_interrupt: float = 0.90
    approval_kinds: tuple[str, ...] = ("approval", "safety")
    max_alternatives: int = 6


@dataclass(frozen=True)
class PolicyRequest:
    situation: Situation
    options: tuple[Action, ...]
    attributes: dict[str, Any] = field(default_factory=dict)


class DecisionPolicy:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()
        self.version = POLICY_VERSION

    # ------------------------------------------------------------------ decide
    def decide(
        self,
        request: PolicyRequest,
        *,
        decision_id: str = "",
        trace_id: str = "",
        created_at: str | None = None,
    ) -> Decision:
        situation = request.situation
        attributes = {**situation.attributes, **request.attributes}
        applied: list[str] = []
        blocked: dict[str, str] = {}

        admitted = self._admit(situation, request.options, applied, blocked)
        by_verb = {verb: [item for item in admitted if item.verb == verb] for verb in VERBS}

        confidence = situation.confidence()
        if "confidence" in attributes:
            confidence = clamp(_number(attributes, "confidence", confidence))
        uncertainty = _number(attributes, "uncertainty", 1.0 - confidence)
        urgency = _number(attributes, "urgency", 0.5)
        sla_breached = _truthy(attributes.get("sla_breached", False))
        verification_due = _truthy(attributes.get("verification_due", False))

        verb: str
        chosen: Action | None = None
        rationale: str

        if self._safety_blocked(situation):
            verb, rationale = "wait", "hard safety constraint blocks action"
        elif sla_breached and by_verb["escalate"]:
            verb, chosen = "escalate", self._best(by_verb["escalate"])
            rationale = "a hard deadline or SLA is already breached"
        elif (uncertainty >= self.config.ask_uncertainty or confidence < self.config.min_confidence) and by_verb["ask"]:
            verb, chosen = "ask", self._best(by_verb["ask"])
            rationale = (
                f"uncertainty {uncertainty:.2f} is at or above {self.config.ask_uncertainty:.2f}"
                if uncertainty >= self.config.ask_uncertainty
                else f"confidence {confidence:.2f} is below the floor {self.config.min_confidence:.2f}"
            )
        elif verification_due and by_verb["verify"]:
            verb, chosen = "verify", self._best(by_verb["verify"])
            rationale = "a previous action has an unverified outcome"
        elif (
            urgency >= self.config.act_urgency
            and confidence >= self.config.act_confidence
            and by_verb["act"]
        ):
            verb, chosen = "act", self._best(by_verb["act"])
            rationale = (
                f"urgency {urgency:.2f} and confidence {confidence:.2f} both clear the act thresholds "
                f"({self.config.act_urgency:.2f}, {self.config.act_confidence:.2f})"
            )
        elif urgency >= self.config.guide_urgency and by_verb["guide"]:
            verb, chosen = "guide", self._best(by_verb["guide"])
            rationale = f"urgency {urgency:.2f} clears the guide threshold {self.config.guide_urgency:.2f} but not act"
        elif by_verb["wait"]:
            verb, chosen = "wait", self._best(by_verb["wait"])
            rationale = "no higher verb is admissible; keep observing"
        elif admitted:
            chosen = self._best(admitted)
            verb = chosen.verb if chosen else "wait"
            rationale = "higher verbs were unavailable; best admissible option selected"
        else:
            verb, rationale = "wait", "no admissible option; keep observing"

        requires_approval = bool(
            chosen
            and (
                chosen.requires_approval
                or chosen.destructive
                or self._approval_required(situation)
            )
        )
        if requires_approval:
            applied.append("approval:human-required")

        alternatives = self._alternatives(request.options, chosen, blocked, applied, verb)
        decision = Decision(
            id=decision_id,
            situation_id=situation.id,
            verb=verb,
            action_id=chosen.id if chosen else None,
            rationale=rationale,
            confidence=confidence,
            alternatives=alternatives,
            constraints_applied=tuple(dict.fromkeys(applied)),
            requires_approval=requires_approval,
            policy_version=self.version,
            created_at=created_at or iso(),
            trace_id=trace_id,
            utility=chosen.utility if chosen else 0.0,
            attributes={
                "urgency": round(urgency, 4),
                "uncertainty": round(uncertainty, 4),
                "sla_breached": sla_breached,
            },
        )
        return decision

    # ------------------------------------------------------------- admission
    def _admit(
        self,
        situation: Situation,
        options: tuple[Action, ...],
        applied: list[str],
        blocked: dict[str, str],
    ) -> list[Action]:
        if self._safety_blocked(situation):
            applied.append("safety:blocked")
            for option in options:
                blocked[option.id] = "blocked by a hard safety constraint"
            return [item for item in options if item.verb == "wait"]

        admitted: list[Action] = []
        for option in options:
            reason = self._violation(situation, option)
            if reason:
                blocked[option.id] = reason
                applied.append(reason)
            else:
                admitted.append(option)
        return admitted

    def _violation(self, situation: Situation, option: Action) -> str | None:
        pairs = (
            ("latency", option.latency_ms, "ms"),
            ("cost", option.cost, ""),
            ("budget", option.cost, ""),
            ("risk", option.risk, ""),
            ("interruption", option.interrupt_cost, ""),
        )
        for kind, amount, unit in pairs:
            constraint = situation.constraint(kind)
            if constraint is None or not constraint.hard:
                continue
            limit = self._limit(kind, constraint.value, amount)
            if limit is None:
                continue
            if amount > limit:
                suffix = f" {unit}" if unit else ""
                return f"blocked by {kind}:{constraint.id} ({amount}{suffix} > {limit}{suffix})"
        return None

    @staticmethod
    def _limit(kind: str, value: Any, amount: float) -> float | None:
        if isinstance(value, dict):
            value = value.get("max", value.get("value"))
        if isinstance(value, bool) or value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        # A risk constraint expressed as "maximum risk" is already normalised.
        if kind == "interruption":
            return numeric if numeric <= 1.0 else numeric / 100.0
        return numeric

    def _safety_blocked(self, situation: Situation) -> bool:
        for constraint in situation.constraints:
            if constraint.kind == "safety" and constraint.hard and _truthy(constraint.value):
                return True
        return False

    def _approval_required(self, situation: Situation) -> bool:
        for constraint in situation.constraints:
            if constraint.kind == "approval" and _truthy(constraint.value):
                return True
        return False

    @staticmethod
    def _best(options: list[Action]) -> Action:
        return sorted(options, key=lambda item: (-item.utility, item.id))[0]

    # ----------------------------------------------------------- explanation
    def _alternatives(
        self,
        options: tuple[Action, ...],
        chosen: Action | None,
        blocked: dict[str, str],
        applied: list[str],
        chosen_verb: str,
    ) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for option in options:
            if chosen is not None and option.id == chosen.id:
                continue
            if option.id in blocked:
                reason = blocked[option.id]
            elif option.verb == chosen_verb:
                reason = "same verb, lower utility"
            else:
                reason = f"not selected; {chosen_verb} won"
            rows.append(
                {
                    "action_id": option.id,
                    "verb": option.verb,
                    "name": option.name,
                    "utility": option.utility,
                    "reason": reason,
                }
            )
        rows.sort(key=lambda item: (-float(item["utility"]), str(item["action_id"])))
        return tuple(rows[: self.config.max_alternatives])


def decide(request: PolicyRequest, *, config: PolicyConfig | None = None, **kwargs: Any) -> Decision:
    """Functional shortcut for hosts that do not need a policy object."""
    return DecisionPolicy(config).decide(request, **kwargs)
