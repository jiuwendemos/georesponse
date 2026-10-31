"""Experience state: goals, phase, beliefs with confidence, decay and expiry.

This is deliberately small.  It stores what the decision needs and nothing
about the host's database.  A host may persist ``snapshot()`` anywhere and
rebuild with ``ExperienceState.from_snapshot``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable

from .contracts import (
    PHASES,
    Belief,
    Constraint,
    Decision,
    Goal,
    Observation,
    clamp,
    confidence_band,
    iso,
    parse_iso,
    utcnow,
)


@dataclass
class ExperienceState:
    subject: str
    phase: str = "observe"
    goals: list[Goal] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    beliefs: dict[str, Belief] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(f"unknown phase: {self.phase}")

    # ------------------------------------------------------------- observation
    def observe(self, observation: Observation, *, half_life_minutes: float = 720.0) -> Belief | None:
        """Record an observation and update a belief when it names a proposition.

        ``payload['proposition']`` and ``payload['confidence']`` are optional.
        Without them the observation is stored and the belief map is unchanged;
        the host adapter decides how domain signals map to propositions.
        """
        self.observations.append(observation)
        self.history.append({"at": observation.at, "event": "observed", "observation": observation.id, "source": observation.source})
        proposition = observation.payload.get("proposition")
        if not proposition:
            return None
        confidence = observation.payload.get("confidence", observation.confidence)
        previous = self.beliefs.get(str(proposition))
        if previous is not None and parse_iso(previous.updated_at) and parse_iso(observation.at):
            # Bayesian-style merge: weight the newer observation by its own
            # confidence, but never let a stale belief keep an inflated score.
            prior = previous.decayed(now=parse_iso(observation.at), half_life_minutes=half_life_minutes)
            merged = clamp(0.55 * float(confidence) + 0.45 * prior)
        else:
            merged = clamp(float(confidence))
        belief = Belief(
            id=str(proposition),
            proposition=str(observation.payload.get("statement", proposition)),
            confidence=merged,
            evidence=(observation.id, *(previous.evidence if previous else ()))[-8:],
            updated_at=observation.at or iso(),
            expires_at=observation.payload.get("expires_at"),
            source=observation.source,
        )
        self.beliefs[belief.id] = belief
        return belief

    def set_belief(self, belief: Belief) -> Belief:
        self.beliefs[belief.id] = belief
        self.history.append({"at": iso(), "event": "belief.updated", "belief": belief.id, "confidence": belief.confidence})
        return belief

    def belief(self, belief_id: str) -> Belief | None:
        return self.beliefs.get(belief_id)

    def confidence(self, belief_ids: Iterable[str] | None = None) -> float:
        items = (
            [self.beliefs[key] for key in belief_ids if key in self.beliefs]
            if belief_ids is not None
            else list(self.beliefs.values())
        )
        if not items:
            return 0.0
        return clamp(min(item.confidence for item in items))

    def band(self, belief_id: str) -> str:
        item = self.beliefs.get(belief_id)
        return confidence_band(item.confidence) if item else "unknown"

    # -------------------------------------------------------------- expiry
    def expire(self, now: datetime | None = None) -> list[str]:
        moment = now or utcnow()
        removed = [key for key, item in self.beliefs.items() if item.expired(moment)]
        for key in removed:
            item = self.beliefs.pop(key)
            self.history.append({"at": iso(moment), "event": "belief.expired", "belief": key, "confidence": item.confidence})
        return removed

    def decay(self, now: datetime | None = None, *, half_life_minutes: float = 720.0) -> None:
        moment = now or utcnow()
        for key, item in list(self.beliefs.items()):
            self.beliefs[key] = Belief(
                id=item.id,
                proposition=item.proposition,
                confidence=item.decayed(moment, half_life_minutes=half_life_minutes),
                evidence=item.evidence,
                updated_at=item.updated_at,
                expires_at=item.expires_at,
                source=item.source,
            )

    # ------------------------------------------------------------- decisions
    def advance(self, phase: str) -> None:
        if phase not in PHASES:
            raise ValueError(f"unknown phase: {phase}")
        self.phase = phase
        self.history.append({"at": iso(), "event": "phase", "phase": phase})

    def record(self, decision: Decision, *, note: str = "") -> None:
        self.history.append(
            {
                "at": decision.created_at,
                "event": "decision",
                "decision": decision.id,
                "verb": decision.verb,
                "action": decision.action_id,
                "note": note,
            }
        )
        self.phase = "act" if decision.verb in {"act", "guide", "ask"} else "decide"

    # ----------------------------------------------------------- persistence
    def snapshot(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "phase": self.phase,
            "goals": [item.to_dict() for item in self.goals],
            "constraints": [item.to_dict() for item in self.constraints],
            "beliefs": [item.to_dict() for item in self.beliefs.values()],
            "history": list(self.history),
            "observations": [item.to_dict() for item in self.observations],
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> "ExperienceState":
        from .contracts import Observation as ObservationContract

        state = cls(subject=str(payload.get("subject", "")))
        state.phase = payload.get("phase", "observe")
        state.goals = [Goal(**item) for item in payload.get("goals", [])]
        state.constraints = [Constraint(**item) for item in payload.get("constraints", [])]
        state.beliefs = {item["id"]: Belief.from_dict(item) for item in payload.get("beliefs", [])}
        state.history = list(payload.get("history", []))
        state.observations = [
            ObservationContract(
                id=item["id"],
                at=item["at"],
                source=item["source"],
                kind=item["kind"],
                confidence=item["confidence"],
                payload=item.get("payload", {}),
                cost=item.get("cost", 0.0),
                latency_ms=item.get("latency_ms", 0),
            )
            for item in payload.get("observations", [])
        ]
        return state

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
