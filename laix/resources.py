"""Resource policy: which perception or model call is worth making.

Two rules, both deterministic:

* cheap detectors run continuously;
* a deep call is admitted only when its expected information gain, weighted by
  the current uncertainty, clears a threshold and the budget still allows it.

The policy reports what it skipped and why, so "deep calls saved" is measured
rather than claimed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .contracts import clamp


@dataclass(frozen=True)
class Budget:
    max_deep_calls: int = 4
    max_cost: float = 1.0
    max_latency_ms: int = 2_000


@dataclass(frozen=True)
class SensingOption:
    name: str
    tier: str = "cheap"  # cheap | deep
    cost: float = 0.0
    latency_ms: int = 0
    information_gain: float = 0.0

    def __post_init__(self) -> None:
        if self.tier not in {"cheap", "deep"}:
            raise ValueError(f"unknown sensing tier: {self.tier}")
        object.__setattr__(self, "information_gain", clamp(self.information_gain))


@dataclass(frozen=True)
class ResourcePlan:
    allowed: tuple[str, ...]
    skipped: tuple[dict[str, Any], ...]
    deep_calls: int
    cost: float
    reason: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": list(self.allowed),
            "skipped": [dict(item) for item in self.skipped],
            "deepCalls": self.deep_calls,
            "cost": round(self.cost, 6),
            "reason": self.reason,
            "attributes": dict(self.attributes),
        }


class ResourcePolicy:
    def __init__(self, *, min_information_gain: float = 0.35) -> None:
        self.min_information_gain = min_information_gain

    def schedule(
        self,
        options: Iterable[SensingOption],
        *,
        budget: Budget | None = None,
        uncertainty: float = 0.5,
    ) -> ResourcePlan:
        budget = budget or Budget()
        uncertainty = clamp(uncertainty)
        allowed: list[str] = []
        skipped: list[dict[str, Any]] = []
        deep_calls = 0
        cost = 0.0

        for option in options:
            if option.tier == "cheap":
                allowed.append(option.name)
                cost += option.cost
                continue
            reason = None
            gain = option.information_gain * max(uncertainty, 0.05)
            if deep_calls >= budget.max_deep_calls:
                reason = "deep-call budget exhausted"
            elif cost + option.cost > budget.max_cost:
                reason = "cost budget exhausted"
            elif option.latency_ms > budget.max_latency_ms:
                reason = "latency budget exceeded"
            elif gain < self.min_information_gain:
                reason = f"information gain {gain:.2f} below threshold {self.min_information_gain:.2f}"
            if reason:
                skipped.append({"name": option.name, "reason": reason, "gain": round(gain, 3)})
                continue
            allowed.append(option.name)
            deep_calls += 1
            cost += option.cost

        return ResourcePlan(
            allowed=tuple(allowed),
            skipped=tuple(skipped),
            deep_calls=deep_calls,
            cost=cost,
            reason="cheap continuous; deep calls admitted by gain, uncertainty and budget",
            attributes={"uncertainty": round(uncertainty, 3), "threshold": self.min_information_gain},
        )

    @staticmethod
    def should_escalate(confidence: float, *, required: float = 0.75) -> bool:
        """The cheap model is not sure enough; ask for the expensive one."""
        return clamp(confidence) < clamp(required)
