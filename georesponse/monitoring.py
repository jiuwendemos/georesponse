"""Recurring monitoring, change alerts and baseline anomaly detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev


def baseline_series(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "std": 0.0, "n": 0}
    return {"mean": round(mean(values), 4), "std": round(pstdev(values), 4), "n": len(values)}


def anomaly_score(value: float, baseline: dict, *, floor_std: float = 0.01) -> float:
    std = max(float(baseline.get("std", 0.0)), floor_std)
    return round((value - float(baseline.get("mean", 0.0))) / std, 3)


def evaluate_region(
    region_id: str,
    observed_change: float,
    history: list[float],
    *,
    threshold_sigma: float = 2.5,
    min_change: float = 0.06,
) -> dict:
    baseline = baseline_series(history)
    z = anomaly_score(observed_change, baseline)
    alert = observed_change >= min_change and z >= threshold_sigma
    return {
        "regionId": region_id,
        "observedChange": round(observed_change, 4),
        "baseline": baseline,
        "zScore": z,
        "thresholdSigma": threshold_sigma,
        "minChange": min_change,
        "alert": alert,
        "severity": "red" if z >= threshold_sigma + 1.5 else "orange" if alert else "none",
        "evaluatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def monitor_regions(regions: list[dict], *, threshold_sigma: float = 2.5) -> list[dict]:
    return [
        evaluate_region(r["id"], float(r["observedChange"]), list(r.get("history", [])), threshold_sigma=threshold_sigma)
        for r in regions
    ]


def save_alerts(alerts: list[dict], path: str | Path) -> None:
    Path(path).write_text(json.dumps({"alerts": alerts}, indent=2), encoding="utf-8")


def build_monitoring_pack(regions: list[dict]) -> dict:
    alerts = monitor_regions(regions)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regions": regions,
        "alerts": alerts,
        "summary": {
            "regions": len(regions),
            "alerts": sum(1 for a in alerts if a["alert"]),
            "red": sum(1 for a in alerts if a["severity"] == "red"),
        },
    }
