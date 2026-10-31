"""Versioned, domain-neutral contracts for the LAIX decision layer.

Nothing in this package may import the host application.  The contracts are the
product: an app describes a situation and the options it can afford, LAIX
returns a decision, a receipt and a measured outcome.

All records are plain dataclasses so they can be serialised to JSON, stored in
any database, or sent over the south interface to an agentic platform without
naming that platform.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"

# The six verbs are the whole north interface.  An app never receives a model
# name, a tool call, or a prompt; it receives one of these decisions.
VERBS: tuple[str, ...] = ("wait", "ask", "guide", "act", "verify", "escalate")

PHASES: tuple[str, ...] = ("observe", "understand", "decide", "act", "verify", "adapt")

HORIZONS: tuple[str, ...] = ("seconds", "minutes", "hours", "days", "weeks")

CONSTRAINT_KINDS: tuple[str, ...] = (
    "latency",
    "cost",
    "risk",
    "interruption",
    "approval",
    "safety",
    "budget",
    "policy",
)

OUTCOME_LABELS: tuple[str, ...] = ("helped", "neutral", "hurt", "unknown")

OUTCOME_DIRECTIONS: tuple[str, ...] = ("higher-better", "lower-better")

RECEIPT_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "executed",
    "refused",
    "cancelled",
    "failed",
    "undone",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def new_receipt_id() -> str:
    return new_id("RCT")


def confidence_band(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.55:
        return "medium"
    return "low"


def to_primitive(value: Any) -> Any:
    """Recursively convert a contract (or a container of them) to JSON types."""
    if is_dataclass(value) and not isinstance(value, type):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    return value


def _tuple_of_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


@dataclass(frozen=True, slots=True)
class Observation:
    """One cheap or expensive measurement of the subject."""

    id: str
    at: str
    source: str
    kind: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0
    latency_ms: int = 0
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", clamp(self.confidence))

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Belief:
    """A proposition the layer currently holds, with confidence and an expiry."""

    id: str
    proposition: str
    confidence: float
    evidence: tuple[str, ...] = ()
    updated_at: str = field(default_factory=iso)
    expires_at: str | None = None
    source: str = "observation"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", clamp(self.confidence))
        object.__setattr__(self, "evidence", _tuple_of_str(self.evidence))

    @property
    def band(self) -> str:
        return confidence_band(self.confidence)

    def expired(self, now: datetime | None = None) -> bool:
        expires = parse_iso(self.expires_at)
        return bool(expires and expires <= (now or utcnow()))

    def decayed(self, now: datetime | None = None, half_life_minutes: float = 720.0) -> float:
        updated = parse_iso(self.updated_at)
        if not updated or half_life_minutes <= 0:
            return self.confidence
        elapsed = ((now or utcnow()) - updated).total_seconds() / 60.0
        if elapsed <= 0:
            return self.confidence
        return clamp(self.confidence * (0.5 ** (elapsed / half_life_minutes)))

    def to_dict(self) -> dict:
        payload = to_primitive(self)
        payload["band"] = self.band
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "Belief":
        data = dict(payload)
        data.pop("band", None)
        if "evidence" in data:
            data["evidence"] = _tuple_of_str(data["evidence"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Goal:
    """What the experience is trying to improve, with an explicit weight."""

    id: str
    statement: str
    priority: float = 0.5
    metric: str = ""
    target: float | None = None
    deadline: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "priority", clamp(self.priority))

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Constraint:
    """A budget, latency, risk, interruption or approval limit.

    ``kind='approval'`` and ``value='required'`` mean a human must approve
    every destructive action.  ``hard=True`` means the policy may not violate
    it; ``hard=False`` means it is a preference used to score options.
    """

    id: str
    kind: str
    value: Any
    hard: bool = True
    statement: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.kind not in CONSTRAINT_KINDS:
            raise ValueError(f"unknown constraint kind: {self.kind}")

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Action:
    """A candidate action the app can afford to offer LAIX.

    The app describes cost, risk and benefit in its own units; LAIX only needs
    comparable numbers and the verb.  Execution is delegated back to the app
    through a named skill, never performed by this package.
    """

    id: str
    verb: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    expected_benefit: float = 0.5
    cost: float = 0.0
    risk: float = 0.0
    latency_ms: int = 0
    interrupt_cost: float = 0.0
    destructive: bool = False
    reversible: bool = True
    requires_approval: bool = False
    addresses: tuple[str, ...] = ()
    rationale: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.verb not in VERBS:
            raise ValueError(f"unknown verb: {self.verb}")
        object.__setattr__(self, "expected_benefit", clamp(self.expected_benefit))
        object.__setattr__(self, "risk", clamp(self.risk))
        object.__setattr__(self, "interrupt_cost", clamp(self.interrupt_cost))
        object.__setattr__(self, "addresses", _tuple_of_str(self.addresses))
        if self.destructive:
            object.__setattr__(self, "requires_approval", True)

    @property
    def utility(self) -> float:
        """Deterministic utility used only to break ties inside one verb band."""
        return round(self.expected_benefit - 0.25 * self.risk - 0.15 * self.interrupt_cost, 6)

    def to_dict(self) -> dict:
        payload = to_primitive(self)
        payload["utility"] = self.utility
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "Action":
        data = dict(payload)
        data.pop("utility", None)
        if "addresses" in data:
            data["addresses"] = _tuple_of_str(data["addresses"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Situation:
    """A snapshot of what is happening, toward which goals, under which limits."""

    id: str
    at: str
    subject: str
    observations: tuple[Observation, ...] = ()
    beliefs: tuple[Belief, ...] = ()
    goals: tuple[Goal, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    phase: str = "observe"
    horizon: str = "minutes"
    attributes: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(f"unknown phase: {self.phase}")
        if self.horizon not in HORIZONS:
            raise ValueError(f"unknown horizon: {self.horizon}")

    def belief(self, belief_id: str) -> Belief | None:
        return next((item for item in self.beliefs if item.id == belief_id), None)

    def constraint(self, kind: str) -> Constraint | None:
        return next((item for item in self.constraints if item.kind == kind), None)

    def confidence(self) -> float:
        if self.beliefs:
            return clamp(min(item.confidence for item in self.beliefs))
        try:
            return clamp(float(self.attributes.get("confidence", 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def uncertainty(self) -> float:
        try:
            return clamp(float(self.attributes.get("uncertainty", 1.0 - self.confidence())))
        except (TypeError, ValueError):
            return 1.0 - self.confidence()

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Decision:
    """One of the six verbs, with the reason and the rejected options."""

    id: str
    situation_id: str
    verb: str
    action_id: str | None
    rationale: str
    confidence: float
    alternatives: tuple[dict[str, Any], ...] = ()
    constraints_applied: tuple[str, ...] = ()
    requires_approval: bool = False
    policy_version: str = ""
    created_at: str = field(default_factory=iso)
    trace_id: str = ""
    utility: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.verb not in VERBS:
            raise ValueError(f"unknown verb: {self.verb}")
        object.__setattr__(self, "confidence", clamp(self.confidence))
        object.__setattr__(self, "alternatives", tuple(dict(item) for item in self.alternatives))
        object.__setattr__(self, "constraints_applied", _tuple_of_str(self.constraints_applied))

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Outcome:
    """Whether a decision helped, measured against a named metric."""

    id: str
    decision_id: str
    metric: str
    before: float
    after: float
    delta: float
    label: str
    attributed: bool = False
    direction: str = "higher-better"
    evidence: dict[str, Any] = field(default_factory=dict)
    measured_at: str = field(default_factory=iso)
    note: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.label not in OUTCOME_LABELS:
            raise ValueError(f"unknown outcome label: {self.label}")
        if self.direction not in OUTCOME_DIRECTIONS:
            raise ValueError(f"unknown outcome direction: {self.direction}")

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Receipt:
    """Proof that an action was executed, refused, cancelled or undone."""

    id: str
    decision_id: str
    action_name: str
    status: str
    actor: str
    at: str = field(default_factory=iso)
    detail: dict[str, Any] = field(default_factory=dict)
    previous_state: dict[str, Any] | None = None
    error: str | None = None
    approved_by: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in RECEIPT_STATUSES:
            raise ValueError(f"unknown receipt status: {self.status}")

    def to_dict(self) -> dict:
        return to_primitive(self)


@dataclass(frozen=True, slots=True)
class Trace:
    """Ordered evidence for one decision: input, policy, execution, outcome."""

    id: str
    decision_id: str
    created_at: str = field(default_factory=iso)
    events: tuple[dict[str, Any], ...] = ()
    schema_version: str = SCHEMA_VERSION

    def with_event(self, stage: str, detail: dict[str, Any] | None = None, *, at: str | None = None) -> "Trace":
        event = {"at": at or iso(), "stage": stage, "detail": detail or {}}
        return Trace(id=self.id, decision_id=self.decision_id, created_at=self.created_at, events=(*self.events, event))

    def to_dict(self) -> dict:
        return to_primitive(self)


CONTRACTS = (
    Observation,
    Belief,
    Goal,
    Constraint,
    Action,
    Situation,
    Decision,
    Outcome,
    Receipt,
    Trace,
)

CONTRACT_NAMES = tuple(item.__name__ for item in CONTRACTS)


def contract_fields(contract: type) -> list[str]:
    return [item.name for item in fields(contract)]
