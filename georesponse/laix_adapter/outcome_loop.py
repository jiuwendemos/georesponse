"""Measure whether a LAIX decision helped, using GeoResponse's own timeline.

No survey is fabricated here.  The loop turns timestamps the store already has
into outcomes and keeps attribution explicit: a time-to-decision improvement is
only attributed when LAIX has a matching execution receipt.
"""

from __future__ import annotations

from laix import Layer, LayerDecision, Outcome, parse_iso

from ..proactive.models import Alert


def _minutes(later: str | None, earlier: str | None) -> float | None:
    first, second = parse_iso(earlier), parse_iso(later)
    if not first or not second:
        return None
    return round((second - first).total_seconds() / 60.0, 3)


class OutcomeLoop:
    def __init__(self, layer: Layer) -> None:
        self.layer = layer

    def _attributed(self, decision: LayerDecision) -> bool:
        return any(
            receipt.decision_id == decision.decision_id and receipt.status == "executed"
            for receipt in self.layer.runtime.receipts()
        )

    def acknowledge_speed(self, decision: LayerDecision, alert: Alert, *, expected_minutes: float) -> Outcome | None:
        actual = _minutes(alert.acknowledged_at, alert.created_at)
        if actual is None:
            return None
        return self.layer.measure(
            decision,
            metric="time_to_acknowledge_minutes",
            before=float(expected_minutes),
            after=actual,
            direction="lower-better",
            attributed=self._attributed(decision),
            evidence={"alertId": alert.id, "acknowledgedAt": alert.acknowledged_at},
            note="SLA window as the reference; attributed only when an execution receipt exists",
        )

    def resolution_speed(self, decision: LayerDecision, alert: Alert, *, expected_minutes: float) -> Outcome | None:
        actual = _minutes(alert.resolved_at, alert.created_at)
        if actual is None:
            return None
        return self.layer.measure(
            decision,
            metric="time_to_resolution_minutes",
            before=float(expected_minutes),
            after=actual,
            direction="lower-better",
            attributed=self._attributed(decision),
            evidence={"alertId": alert.id, "resolvedAt": alert.resolved_at},
        )

    def analyst_feedback(self, decision: LayerDecision, *, verdict: str, note: str = "") -> Outcome:
        """Record a human label.  It is useful, but it is not causal proof."""
        normalised = verdict.strip().lower()
        label = "helped" if normalised in {"useful", "correct", "true-positive"} else "hurt"
        return self.layer.measure(
            decision,
            metric="analyst_verdict",
            before=0.0,
            after=1.0 if label == "helped" else 0.0,
            attributed=False,
            evidence={"verdict": verdict},
            note=note or "analyst label; excluded from attributed gain",
            label=label,
        )

    def summary(self) -> dict:
        return self.layer.runtime.outcomes.summary()
