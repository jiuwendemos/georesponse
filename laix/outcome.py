"""Outcome learning: did the decision actually help?

This module records measured outcomes, not clicks.  Attribution is explicit:
``attributed=True`` means the host can defend that the action caused the change;
otherwise the label is still recorded but excluded from the attributed summary.

Metrics have a direction.  ``time_to_assessment`` improves when it falls;
``precision`` improves when it rises.  Without that, a faster decision would be
scored as a regression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .contracts import OUTCOME_DIRECTIONS, OUTCOME_LABELS, Outcome, iso, new_id


def _signed_gain(delta: float, direction: str) -> float:
    return delta if direction == "higher-better" else -delta


def _label(delta: float, tolerance: float, direction: str) -> str:
    gain = _signed_gain(delta, direction)
    if gain > tolerance:
        return "helped"
    if gain < -tolerance:
        return "hurt"
    return "neutral"


@dataclass
class OutcomeLedger:
    tolerance: float = 1e-9
    records: list[Outcome] = field(default_factory=list)

    def record(
        self,
        decision_id: str,
        *,
        metric: str,
        before: float,
        after: float,
        attributed: bool = False,
        direction: str = "higher-better",
        evidence: dict[str, Any] | None = None,
        note: str = "",
        label: str | None = None,
        measured_at: str | None = None,
        tolerance: float | None = None,
    ) -> Outcome:
        if direction not in OUTCOME_DIRECTIONS:
            raise ValueError(f"unknown outcome direction: {direction}")
        delta = round(float(after) - float(before), 6)
        resolved = label or _label(delta, tolerance if tolerance is not None else self.tolerance, direction)
        if resolved not in OUTCOME_LABELS:
            raise ValueError(f"unknown outcome label: {resolved}")
        outcome = Outcome(
            id=new_id("OUT"),
            decision_id=decision_id,
            metric=metric,
            before=float(before),
            after=float(after),
            delta=delta,
            label=resolved,
            attributed=bool(attributed),
            direction=direction,
            evidence=dict(evidence or {}),
            measured_at=measured_at or iso(),
            note=note,
        )
        self.records.append(outcome)
        return outcome

    def for_decision(self, decision_id: str) -> list[Outcome]:
        return [item for item in self.records if item.decision_id == decision_id]

    def summary(self) -> dict[str, Any]:
        """Measured gain, with attribution coverage stated separately."""
        attributed = [item for item in self.records if item.attributed]
        improved = [item for item in attributed if item.label == "helped"]
        hurt = [item for item in attributed if item.label == "hurt"]
        gains = [_signed_gain(item.delta, item.direction) for item in attributed]
        return {
            "measured": len(self.records),
            "attributed": len(attributed),
            "attributionCoverage": round(len(attributed) / max(1, len(self.records)), 3),
            "helped": len(improved),
            "neutral": len([item for item in attributed if item.label == "neutral"]),
            "hurt": len(hurt),
            "meanGain": round(sum(gains) / len(gains), 6) if gains else 0.0,
            "precision": round(len(improved) / max(1, len(attributed)), 3),
        }

    def by_metric(self) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for item in self.records:
            bucket = rows.setdefault(
                item.metric,
                {"measured": 0, "attributed": 0, "helped": 0, "hurt": 0, "gain": 0.0},
            )
            bucket["measured"] += 1
            if item.attributed:
                bucket["attributed"] += 1
                bucket["helped"] += int(item.label == "helped")
                bucket["hurt"] += int(item.label == "hurt")
                bucket["gain"] += _signed_gain(item.delta, item.direction)
        for bucket in rows.values():
            bucket["gain"] = round(bucket["gain"], 6)
        return rows

    def extend(self, records: Iterable[Outcome]) -> None:
        self.records.extend(records)

    def to_dict(self) -> dict[str, Any]:
        return {"tolerance": self.tolerance, "records": [item.to_dict() for item in self.records], "summary": self.summary()}
