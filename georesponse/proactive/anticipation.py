"""Forecast ingestion, pre-event watchlists, lead time and scenario simulation.

Anticipation is the phase after detection is trustworthy.  The output is a
*watchlist* and a tasking trigger, never an automatic dispatch.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Forecast, Scope, clamp, hours_since, new_id, now_iso, parse_iso, utcnow
from .store import ProactiveStore

SEASONAL_CALENDAR = {
    "ahr": [
        {"months": [5, 6, 7, 8], "risk": "flood", "label": "Summer convective flood"},
        {"months": [6, 7, 8], "risk": "wildfire", "label": "Dry ridge wildfire"},
        {"months": [11, 12, 1, 2], "risk": "freeze", "label": "Freeze and burst pipes"},
    ],
    "eifel": [
        {"months": [6, 7, 8], "risk": "wildfire", "label": "Forest fire season"},
        {"months": [12, 1, 2], "risk": "storm", "label": "Winter storm"},
    ],
    "cologne": [
        {"months": [3, 4, 5, 6, 7, 8, 9], "risk": "construction", "label": "Construction season"},
        {"months": [6, 7, 8], "risk": "storm", "label": "Summer storm"},
    ],
    "default": [
        {"months": [3, 4, 5, 6, 7, 8, 9], "risk": "construction", "label": "Construction season"},
        {"months": [11, 12, 1, 2], "risk": "storm", "label": "Winter storm"},
    ],
}


def ingest_forecast(payload: dict) -> Forecast:
    hazard = payload.get("hazard", "flood")
    probability = clamp(float(payload.get("probability", 0.5)), 0.0, 1.0)
    uncertainty = clamp(float(payload.get("uncertainty", 0.2)), 0.0, 0.9)
    issued = payload.get("issuedAt") or now_iso()
    valid_from = payload.get("validFrom") or issued
    valid_to = payload.get("validTo") or (
        (parse_iso(valid_from) or utcnow()) + timedelta(hours=48)
    ).isoformat(timespec="seconds")
    return Forecast(
        id=payload.get("id") or new_id("fc"),
        region=payload.get("region", ""),
        issued_at=issued,
        valid_from=valid_from,
        valid_to=valid_to,
        hazard=hazard,
        probability=probability,
        rainfall_mm=float(payload.get("rainfallMm", 0.0)),
        wind_kmh=float(payload.get("windKmh", 0.0)),
        river_level_m=float(payload.get("riverLevelM", 0.0)),
        uncertainty=uncertainty,
        source=payload.get("source", "demo-forecast"),
        confidence=clamp(1 - uncertainty, 0.0, 0.99),
        metadata=payload.get("metadata", {}),
    )


def _forecast_matches(scope: Scope, forecast: Forecast) -> bool:
    a, b = scope.region.lower(), forecast.region.lower()
    return bool(a and b and (a in b or b in a))


def lead_time_hours(forecast: Forecast, *, distance_km: float = 12.0, response_speed_kmh: float = 12.0) -> float:
    hazard_factor = {"flood": 1.0, "storm": 1.4, "wildfire": 0.8, "construction": 3.0}.get(forecast.hazard, 1.0)
    travel = distance_km / response_speed_kmh
    forecast_lead = 6 + 24 * forecast.probability
    return round(max(0.5, (forecast_lead - travel) * hazard_factor * (1 - forecast.uncertainty * 0.3)), 1)


def _exposure(scope: Scope) -> dict:
    assets = scope.metadata.get("assets", [])
    value = int(scope.metadata.get("valueEur", 0) or sum(int(a.get("valueEur", 0)) for a in assets))
    population = int(scope.metadata.get("population", 0) or sum(int(a.get("population", 0)) for a in assets))
    critical = sum(1 for a in assets if a.get("critical"))
    return {"valueEur": value, "population": population, "criticalAssets": critical, "assets": len(assets)}


def score_watch(scope: Scope, forecast: Forecast) -> dict:
    exposure = _exposure(scope)
    value_score = clamp(math.log10(max(1, exposure["valueEur"])) / 8, 0, 1)
    population_score = clamp(math.log10(max(1, exposure["population"])) / 5, 0, 1)
    lead = lead_time_hours(forecast)
    urgency = clamp(1 - lead / 72, 0.05, 1)
    score = round(
        0.34 * forecast.probability
        + 0.22 * value_score
        + 0.16 * population_score
        + 0.16 * urgency
        + 0.12 * (1 / max(1, scope.priority)),
        4,
    )
    return {
        "score": score,
        "leadTimeHours": lead,
        "exposure": exposure,
        "urgency": round(urgency, 3),
        "probability": forecast.probability,
        "confidence": forecast.confidence,
    }


def pre_event_watchlist(store: ProactiveStore, tenant: str, forecasts: list[Forecast], *, now: datetime | None = None) -> list[dict]:
    moment = now or utcnow()
    rows = []
    for scope in store.list_scopes(tenant=tenant, status="active"):
        matches = [f for f in forecasts if _forecast_matches(scope, f)]
        if not matches:
            continue
        forecast = max(matches, key=lambda f: f.probability)
        scored = score_watch(scope, forecast)
        low = round(max(0, forecast.probability - forecast.uncertainty), 3)
        high = round(min(1, forecast.probability + forecast.uncertainty), 3)
        rows.append(
            {
                "scopeId": scope.id,
                "name": scope.name,
                "region": scope.region,
                "hazard": forecast.hazard,
                "probability": forecast.probability,
                "interval": [low, high],
                "uncertainty": forecast.uncertainty,
                "leadTimeHours": scored["leadTimeHours"],
                "score": scored["score"],
                "urgency": scored["urgency"],
                "exposure": scored["exposure"],
                "validTo": forecast.valid_to,
                "forecastId": forecast.id,
                "recommendation": preposition(scope, forecast),
                "taskingTrigger": tasking_trigger(forecast),
                "status": "watch",
                "computedAt": now_iso(moment),
            }
        )
    return sorted(rows, key=lambda row: -row["score"])


def tasking_trigger(forecast: Forecast) -> bool:
    return forecast.probability >= 0.55 and forecast.uncertainty <= 0.35


def preposition(scope: Scope, forecast: Forecast) -> dict:
    exposure = _exposure(scope)
    teams = 1 if forecast.probability < 0.6 else 2 if forecast.probability < 0.8 else 3
    return {
        "teams": teams,
        "note": "Recommendation only. A human commits the teams.",
        "prioritySites": exposure["criticalAssets"],
        "reason": f"{forecast.hazard} probability {round(forecast.probability * 100)}% with {round(forecast.uncertainty * 100)}% uncertainty",
    }


def seasonal_calendar(region: str, month: int | None = None) -> dict:
    month = month or utcnow().month
    key = "default"
    for candidate in SEASONAL_CALENDAR:
        if candidate != "default" and candidate in region.lower():
            key = candidate
            break
    entries = [entry for entry in SEASONAL_CALENDAR[key] if month in entry["months"]]
    return {
        "region": region,
        "month": month,
        "risks": entries,
        "summary": entries[0]["label"] if entries else "No seasonal risk on the calendar",
    }


def portfolio_heatmap(store: ProactiveStore, tenant: str, forecasts: list[Forecast]) -> list[dict]:
    rows = []
    for scope in store.list_scopes(tenant):
        matches = [f for f in forecasts if _forecast_matches(scope, f)]
        forecast = max(matches, key=lambda f: f.probability) if matches else None
        exposure = _exposure(scope)
        probability = forecast.probability if forecast else 0.0
        rows.append(
            {
                "scopeId": scope.id,
                "name": scope.name,
                "region": scope.region,
                "probability": probability,
                "valueEur": exposure["valueEur"],
                "population": exposure["population"],
                "riskScore": round(probability * (0.6 + 0.4 * clamp(math.log10(max(1, exposure["valueEur"])) / 8, 0, 1)), 3),
                "hazard": forecast.hazard if forecast else None,
            }
        )
    return sorted(rows, key=lambda row: -row["riskScore"])


def _asset_ground(asset: dict) -> float:
    if asset.get("groundM") is not None:
        return float(asset["groundM"])
    digest = hashlib.sha256(asset.get("id", "").encode("utf-8")).hexdigest()
    return 2.0 + (int(digest[:4], 16) % 40) / 10


def simulate_scenario(scope: Scope, *, water_level_m: float, threshold_m: float = 2.0, assets: list[dict] | None = None) -> dict:
    assets = assets or scope.metadata.get("assets", [])
    submerged = []
    for asset in assets:
        if water_level_m >= _asset_ground(asset):
            submerged.append(asset)
    value = sum(int(a.get("valueEur", 0)) for a in submerged)
    population = sum(int(a.get("population", 0)) for a in submerged)
    return {
        "scopeId": scope.id,
        "scenario": f"water level {water_level_m} m",
        "submerged": len(submerged),
        "assets": [a.get("name", a.get("id", "asset")) for a in submerged],
        "valueEur": value,
        "population": population,
        "cutOff": round(min(1.0, water_level_m / max(threshold_m, 0.1) * 0.4), 2),
        "note": "Scenario input, not a forecast. Human review required.",
    }


def digest_since(store: ProactiveStore, tenant: str, *, hours: int = 24, now: datetime | None = None) -> dict:
    moment = now or utcnow()
    cutoff = (moment - timedelta(hours=hours)).isoformat(timespec="seconds")
    alerts = [a for a in store.list_alerts(tenant) if a.created_at >= cutoff]
    resolved = [a for a in alerts if a.status == "resolved"]
    dismissed = [a for a in alerts if a.status == "dismissed"]
    return {
        "periodHours": hours,
        "alerts": len(alerts),
        "resolved": len(resolved),
        "dismissed": len(dismissed),
        "open": len([a for a in alerts if a.status not in {"resolved", "dismissed"}]),
        "bySeverity": {severity: sum(1 for a in alerts if a.severity == severity) for severity in ("red", "orange", "yellow")},
        "headlines": [a.title for a in alerts[:5]],
        "noAction": len([a for a in dismissed if a.dismissed_reason == "no_action"]),
        "generatedAt": now_iso(moment),
    }


def reconcile(forecast: Forecast, observed_at: str | None, observed_value: float, threshold: float) -> dict:
    if not observed_at:
        return {"result": "miss", "leadTimeHours": None, "forecastProbability": forecast.probability}
    lead = max(0.0, hours_since(forecast.issued_at, parse_iso(observed_at)))
    return {
        "result": "hit" if observed_value >= threshold else "false-alarm",
        "leadTimeHours": round(lead, 1),
        "forecastProbability": forecast.probability,
        "observed": observed_value,
        "threshold": threshold,
    }


def watch_now_plan(store: ProactiveStore, tenant: str, forecasts: list[Forecast]) -> dict:
    watch = pre_event_watchlist(store, tenant, forecasts)
    return {
        "watchlist": watch,
        "tasking": [row["scopeId"] for row in watch if row["taskingTrigger"]],
        "generatedAt": now_iso(),
        "note": "Tasking is queued for human approval; no automatic dispatch.",
    }
