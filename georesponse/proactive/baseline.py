"""Baselines, trend classification, confirmation and drift.

The detector is not a black box: an alert is the result of a threshold, a
baseline, a confirmation rule, a suppression factor and a calibrated
confidence.  Every one of those is returned with the finding.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Baseline, MonitoringPlan, Scope, clamp, now_iso, parse_iso, utcnow
from .store import ProactiveStore

STANDARD_THRESHOLDS = {"red": 0.72, "orange": 0.45, "yellow": 0.0}
ASSET_SIGMA_ADJUST = {
    "utility + emergency": -0.2,
    "utility": -0.1,
    "insurance": 0.0,
    "agriculture": 0.2,
    "mining": -0.15,
    "construction": 0.1,
}
SEASON_SUPPRESSION = {"winter": 0.18, "spring": 0.04, "summer": 0.02, "autumn": 0.06}


def season_for(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    xs = list(range(n))
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(values)
    denom = sum((x - mean_x) ** 2 for x in xs) or 1
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom


def trend_of(values: list[float], tolerance: float = 0.005) -> str:
    slope = linear_slope(values)
    if slope > tolerance:
        return "increasing"
    if slope < -tolerance:
        return "decreasing"
    return "stable"


def abruptness(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    std = statistics.pstdev(values[:-1]) or 0.001
    return (values[-1] - statistics.mean(values[:-1])) / std


def temporal_confirmation(history: list[bool], required: int = 2) -> bool:
    return sum(1 for value in history[-max(1, required * 2) :] if value) >= required


def cross_sensor_confidence(optical: float, sar: float, *, optical_available: bool = True, sar_available: bool = True) -> dict:
    if optical_available and sar_available:
        agreement = 1 - abs(optical - sar)
        confidence = round(clamp(0.55 * optical + 0.3 * sar + 0.15 * agreement, 0.0, 0.99), 3)
        return {"confidence": confidence, "agreement": round(agreement, 3), "method": "optical+sar"}
    if optical_available:
        return {"confidence": round(optical, 3), "agreement": None, "method": "optical-only"}
    return {"confidence": round(sar, 3), "agreement": None, "method": "sar-only"}


def adaptive_threshold(scope: Scope, plan: MonitoringPlan, baseline: Baseline | None, season: str) -> dict:
    sigma = plan.threshold_sigma + ASSET_SIGMA_ADJUST.get(scope.asset_class, 0.0)
    sigma = max(1.2, sigma)
    base = baseline.mean if baseline else 0.0
    std = max(baseline.std if baseline else 0.0, 0.005)
    threshold = base + sigma * std
    min_change = plan.min_change
    if scope.kind == "portfolio":
        min_change *= 0.9
    if scope.kind == "corridor":
        min_change *= 1.1
    suppression = SEASON_SUPPRESSION.get(season, 0.04)
    return {
        "sigma": round(sigma, 2),
        "mean": round(base, 5),
        "std": round(std, 5),
        "threshold": round(threshold, 5),
        "minChange": round(min_change, 4),
        "season": season,
        "seasonSuppression": suppression,
    }


def suppression_factor(*, cloud: float = 0.0, shadow: float = 0.0, snow: float = 0.0, season: str = "summer") -> float:
    factor = 1.0
    factor -= min(0.55, cloud * 1.3)
    factor -= min(0.25, shadow * 1.2)
    factor -= min(0.3, snow * 1.4)
    factor -= SEASON_SUPPRESSION.get(season, 0.04)
    return round(max(0.0, factor), 3)


def detect_construction(change_fraction: float, months: int, threshold: float = 0.05) -> dict:
    persistent = months >= 2 and change_fraction >= threshold
    return {
        "type": "construction",
        "persistent": persistent,
        "months": months,
        "changeFraction": round(change_fraction, 4),
        "alert": persistent,
    }


def detect_vegetation(values: list[float], *, drought_drop: float = -0.08) -> dict:
    if len(values) < 2:
        return {"type": "vegetation", "alert": False, "delta": 0.0, "trend": "stable"}
    delta = values[-1] - statistics.mean(values[:-1])
    trend = trend_of(values, tolerance=0.01)
    return {
        "type": "vegetation",
        "alert": delta <= drought_drop,
        "delta": round(delta, 4),
        "trend": trend,
        "ndvi": round(values[-1], 4),
    }


def detect_erosion(values: list[float], *, threshold: float = 0.02) -> dict:
    if len(values) < 3:
        return {"type": "erosion", "alert": False, "slope": 0.0}
    slope = linear_slope(values)
    return {"type": "erosion", "alert": slope >= threshold, "slope": round(slope, 5), "series": [round(v, 4) for v in values]}


def quiet_period(last_event_at: str | None, *, hours: int = 6, now: datetime | None = None) -> bool:
    moment = now or utcnow()
    start = parse_iso(last_event_at)
    if not start:
        return False
    return moment - start < timedelta(hours=hours)


class BaselineEngine:
    def __init__(self, store: ProactiveStore) -> None:
        self.store = store

    def update(self, scope: Scope, metric: str, value: float, *, model_version: str = "", max_points: int = 60) -> Baseline:
        baseline = self.store.get_baseline(scope.id, metric) or Baseline(scope_id=scope.id, metric=metric)
        baseline.values = (baseline.values + [round(float(value), 6)])[-max_points:]
        baseline.season = season_for(utcnow().month)
        baseline.model_version = model_version
        baseline.updated_at = now_iso()
        baseline.recompute()
        baseline.trend = trend_of(baseline.values)
        self.store.save_baseline(baseline)
        return baseline

    def evaluate(self, scope: Scope, plan: MonitoringPlan, observation: dict) -> dict:
        metric = observation.get("metric", "change_fraction")
        value = float(observation.get("changeFraction", observation.get("value", 0.0)))
        baseline = self.store.get_baseline(scope.id, metric) or Baseline(scope_id=scope.id, metric=metric).recompute()
        season = observation.get("season") or season_for(utcnow().month)
        threshold = adaptive_threshold(scope, plan, baseline, season)
        history = baseline.values + [value]
        observed = value >= max(threshold["minChange"], threshold["threshold"])
        temporal = temporal_confirmation([v >= threshold["minChange"] for v in history], required=2)
        optical = float(observation.get("opticalConfidence", observation.get("confidence", 0.6)))
        sar = float(observation.get("sarConfidence", 0.0))
        fusion = cross_sensor_confidence(
            optical,
            sar,
            optical_available=bool(observation.get("optical", True)),
            sar_available=bool(observation.get("sar", False)),
        )
        suppress = suppression_factor(
            cloud=float(observation.get("cloud", 0.0)),
            shadow=float(observation.get("shadow", 0.0)),
            snow=float(observation.get("snow", 0.0)),
            season=season,
        )
        confidence = round(clamp(fusion["confidence"] * (0.55 + 0.45 * suppress) * (1.0 if temporal else 0.72), 0.0, 0.99), 3)
        trend = trend_of(history)
        alert = bool(observed and temporal and suppress >= 0.35 and confidence >= 0.45 and not quiet_period(observation.get("lastEventAt")))
        return {
            "scopeId": scope.id,
            "metric": metric,
            "observed": round(value, 5),
            "baseline": threshold,
            "trend": trend,
            "abruptness": round(abruptness(history), 3),
            "temporalConfirmation": temporal,
            "fusion": fusion,
            "suppression": suppress,
            "confidence": confidence,
            "alert": alert,
            "reason": "change confirmed across observations" if alert else "below threshold, unconfirmed, suppressed or quiet period",
            "history": [round(v, 4) for v in history[-12:]],
            "season": season,
            "modelVersion": observation.get("modelVersion", ""),
        }

    def observe_and_store(self, scope: Scope, plan: MonitoringPlan, observation: dict) -> dict:
        finding = self.evaluate(scope, plan, observation)
        self.update(
            scope,
            observation.get("metric", "change_fraction"),
            float(observation.get("changeFraction", observation.get("value", 0.0))),
            model_version=observation.get("modelVersion", ""),
        )
        return finding


def drift_score(reference: list[float], recent: list[float]) -> dict:
    if not reference or not recent:
        return {"score": 0.0, "flag": False, "reason": "insufficient data"}
    ref_mean, ref_std = statistics.mean(reference), statistics.pstdev(reference) or 0.001
    recent_mean = statistics.mean(recent)
    z = (recent_mean - ref_mean) / ref_std
    return {
        "score": round(abs(z), 3),
        "direction": "up" if z > 0 else "down",
        "flag": abs(z) >= 2.5,
        "referenceMean": round(ref_mean, 4),
        "recentMean": round(recent_mean, 4),
    }


def backtest(predictions: Iterable[dict]) -> dict:
    rows = list(predictions)
    tp = sum(1 for r in rows if r.get("predicted") and r.get("actual"))
    fp = sum(1 for r in rows if r.get("predicted") and not r.get("actual"))
    fn = sum(1 for r in rows if not r.get("predicted") and r.get("actual"))
    tn = sum(1 for r in rows if not r.get("predicted") and not r.get("actual"))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    brier = sum((float(r.get("confidence", 0.5)) - (1 if r.get("actual") else 0)) ** 2 for r in rows) / max(1, len(rows))
    return {
        "rows": len(rows),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precision * recall / max(1e-9, precision + recall), 3),
        "brier": round(brier, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def calibration(confidences: list[float], outcomes: list[bool], bins: int = 5) -> list[dict]:
    rows = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(c, o) for c, o in zip(confidences, outcomes) if low <= c < high or (index == bins - 1 and c == 1.0)]
        if not members:
            rows.append({"bin": f"{int(low*100)}-{int(high*100)}%", "n": 0, "meanConfidence": None, "observedRate": None})
            continue
        rows.append(
            {
                "bin": f"{int(low*100)}-{int(high*100)}%",
                "n": len(members),
                "meanConfidence": round(statistics.mean(c for c, _ in members), 3),
                "observedRate": round(sum(1 for _, o in members if o) / len(members), 3),
            }
        )
    return rows


def apply_feedback(store: ProactiveStore, scope: Scope) -> dict:
    """Adjust a scope's confidence offset from analyst decisions."""
    decisions = store.list_validations(scope.id)
    if not decisions:
        return {"scopeId": scope.id, "offset": 0.0, "samples": 0}
    rejected = sum(1 for d in decisions if d["decision"] == "rejected")
    rate = rejected / len(decisions)
    offset = round(clamp(-0.25 * rate, -0.2, 0.05), 3)
    store.meta_set(f"calibration:{scope.id}", str(offset))
    return {"scopeId": scope.id, "offset": offset, "samples": len(decisions), "rejectionRate": round(rate, 3)}
