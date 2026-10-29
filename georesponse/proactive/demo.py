"""Demo data for the proactive Watch UI and API.

Builds an in-memory store, seeds a realistic multi-sector watch portfolio, and
serializes the same objects the scheduler and engine use.  This is demo data,
clearly labelled; the algorithms and lifecycle are real.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import alerts as alert_ops
from .baseline import BaselineEngine
from .engine import ProactiveEngine
from .governance import KillSwitch, alert_quality, governance_snapshot
from .models import (
    Acquisition,
    Alert,
    Baseline,
    CostEntry,
    Forecast,
    Incident,
    ModelEntry,
    MonitoringPlan,
    Notification,
    Scope,
    TenantPreferences,
    ValidationRecord,
    new_id,
    now_iso,
    utcnow,
)
from .notifications import preferences_payload
from .scheduler import calendar, cost_report
from .store import ProactiveStore

TENANT = "demo"


def _ago(hours: float) -> str:
    return (utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds")


def _ahead(hours: float) -> str:
    return (utcnow() + timedelta(hours=hours)).isoformat(timespec="seconds")


def _scope(
    scope_id: str,
    name: str,
    kind: str,
    region: str,
    center: tuple[float, float],
    bbox: tuple[float, float, float, float],
    asset_class: str,
    change_types: list[str],
    cadence: str,
    priority: int,
    *,
    status: str = "active",
    value: int = 5_000_000,
    population: int = 500,
    assets: list[dict] | None = None,
) -> Scope:
    return Scope(
        id=scope_id,
        tenant=TENANT,
        name=name,
        kind=kind,
        region=region,
        center=center,
        bbox=bbox,
        asset_class=asset_class,
        change_types=change_types,
        cadence=cadence,
        priority=priority,
        subscription_tier={"6h": "24-7", "12h": "daily", "daily": "daily", "weekly": "weekly"}.get(cadence, "weekly"),
        status=status,
        freshness_slo_hours={"6h": 12, "12h": 24, "daily": 48, "weekly": 168}.get(cadence, 168),
        tags=["proactive", asset_class],
        metadata={"valueEur": value, "population": population, "assets": assets or []},
    )


def _plan(scope: Scope, *, digest: str = "instant", recipients: list[str] | None = None, budget: float = 2500) -> MonitoringPlan:
    return MonitoringPlan(
        scope_id=scope.id,
        cadence=scope.cadence,
        recipients=recipients or ["ops@example.com", "claims@example.com"],
        digest=digest,
        budget_eur_per_month=budget,
        sla_hours=4 if scope.priority <= 2 else 8,
        first_n_alerts_require_analyst=3,
        escalation=[
            {"scopeId": scope.id, "minSeverity": "red", "team": "incident", "assignee": "A. Weber"},
            {"scopeId": scope.id, "team": "watch", "assignee": "M. Keller"},
        ],
    )


def _baseline(scope_id: str, metric: str, values: list[float], *, season: str = "summer") -> Baseline:
    baseline = Baseline(scope_id=scope_id, metric=metric, values=values, season=season, model_version="gr-changenet-1.4.2")
    baseline.recompute()
    return baseline


def _alert(
    *,
    alert_id: str,
    scope: Scope,
    title: str,
    summary: str,
    severity: str,
    change_type: str,
    confidence: float,
    observed: float,
    baseline: float,
    lon: float,
    lat: float,
    status: str,
    assignee: str | None,
    incident_id: str | None,
    asset: str,
    value: int,
    population: int,
    access: str,
    created_hours_ago: float,
    sla_hours: float = 4,
    dismissed_reason: str | None = None,
    validated: bool = False,
    evidence: dict | None = None,
    lead_time: float = 9.4,
) -> Alert:
    created = _ago(created_hours_ago)
    alert = Alert(
        id=alert_id,
        tenant=TENANT,
        scope_id=scope.id,
        title=title,
        summary=summary,
        severity=severity,
        urgency=0.0,
        confidence=confidence,
        change_type=change_type,
        observed=observed,
        baseline=baseline,
        lon=lon,
        lat=lat,
        incident_id=incident_id,
        status=status,
        assignee=assignee,
        sla_due=(datetime.fromisoformat(created) + timedelta(hours=sla_hours)).isoformat(timespec="seconds"),
        created_at=created,
        asset=asset,
        value_eur=value,
        population=population,
        access=access,
        source="sentinel-2",
        model_version="gr-changenet-1.4.2",
        evidence=evidence
        or {
            "before": "data/scenes/ahr-2021-flood-before.png",
            "after": "data/scenes/ahr-2021-flood-after.png",
        },
        why={
            "summary": f"{round(observed*100, 1)}% change against a {round(baseline*100, 1)}% baseline",
            "threshold": {"mean": baseline, "threshold": baseline + 0.04, "sigma": 2.5, "minChange": 0.06},
            "trend": "increasing",
            "abruptness": 2.7,
            "confirmation": True,
            "fusion": {"confidence": confidence, "agreement": 0.89, "method": "optical+sar"},
            "suppression": 0.92,
            "leadTimeHours": lead_time,
            "scope": {"name": scope.name, "kind": scope.kind, "assetClass": scope.asset_class},
        },
        provenance={
            "imagery": "Simulated Sentinel-2 L2A-like composite",
            "acquired": _ago(created_hours_ago + 2),
            "model": "gr-changenet-1.4.2",
            "baseline": {"mean": baseline, "sigma": 2.5},
        },
        validated_by="A. Weber" if validated else None,
        validation_count=3 if validated else 0,
        tags=["demo", change_type],
        dismissed_reason=dismissed_reason,
    )
    alert_ops.urgency_score(alert)
    return alert


def _incident(incident_id: str, scope: Scope, title: str, severity: str, status: str, alert_ids: list[str], assignee: str | None) -> Incident:
    return Incident(
        id=incident_id,
        tenant=TENANT,
        scope_id=scope.id,
        title=title,
        severity=severity,
        status=status,
        alert_ids=alert_ids,
        assignee=assignee,
        opened_at=_ago(5),
        summary=f"{len(alert_ids)} related alert(s) in {scope.name}. Human review required.",
        timeline=[
            {"at": _ago(5), "event": "incident.opened", "alertId": alert_ids[0] if alert_ids else None},
            {"at": _ago(4), "event": "alert.acknowledged", "alertId": alert_ids[0] if alert_ids else None, "actor": "A. Weber"},
        ],
    )


def seed_demo(store: ProactiveStore) -> dict:
    scopes = [
        _scope(
            "scope-ahr-corridor", "Ahr corridor watch", "corridor", "Ahrweiler, Germany",
            (7.10, 50.545), (7.043, 50.522, 7.157, 50.567), "utility + emergency",
            ["flood", "erosion", "construction"], "daily", 1, value=56_200_000, population=9_630,
            assets=[
                {"id": "S02", "name": "Bad Neuenahr care campus", "valueEur": 6_200_000, "population": 1800, "critical": True, "groundM": 2.1},
                {"id": "S04", "name": "Heppingen substation", "valueEur": 8_400_000, "population": 640, "critical": True, "groundM": 2.6},
                {"id": "S03", "name": "Heimersheim bridge park", "valueEur": 4_200_000, "population": 900, "critical": False, "groundM": 2.3},
                {"id": "S01", "name": "Ahrweiler Altstadt", "valueEur": 4_800_000, "population": 2100, "critical": False, "groundM": 2.0},
            ],
        ),
        _scope(
            "scope-rur-utility", "Rur valley utility corridor", "corridor", "Rur valley, Germany",
            (6.42, 50.76), (6.35, 50.72, 6.49, 50.80), "utility",
            ["vegetation", "flood", "erosion"], "daily", 2, value=18_400_000, population=2_100,
            assets=[{"id": "R01", "name": "Rur pump station", "valueEur": 7_100_000, "population": 300, "critical": True, "groundM": 1.8}],
        ),
        _scope(
            "scope-cologne-construction", "Cologne construction watch", "portfolio", "Cologne, Germany",
            (6.905, 50.935), (6.84, 50.89, 6.97, 50.98), "construction",
            ["construction", "structure"], "weekly", 3, value=42_000_000, population=5_400,
            assets=[{"id": "C03", "name": "Ehrenfeld yard", "valueEur": 12_000_000, "population": 400, "critical": False, "groundM": 9.0}],
        ),
        _scope(
            "scope-eifel-fire", "Eifel ridge wildfire watch", "aoi", "Eifel, Germany",
            (6.42, 50.59), (6.35, 50.54, 6.49, 50.65), "insurance",
            ["wildfire", "vegetation"], "12h", 2, value=11_800_000, population=1_250,
            assets=[{"id": "E11", "name": "Vogelsang forest block", "valueEur": 4_400_000, "population": 120, "critical": False, "groundM": 4.0}],
        ),
        _scope(
            "scope-dernau-vineyard", "Dernau vineyard block", "asset", "Dernau, Germany",
            (7.05, 50.53), (7.03, 50.515, 7.07, 50.545), "agriculture",
            ["vegetation", "flood"], "weekly", 4, value=2_800_000, population=180,
            assets=[{"id": "D08", "name": "Dernau vineyard terraces", "valueEur": 2_800_000, "population": 180, "critical": False, "groundM": 2.2}],
        ),
        _scope(
            "scope-tailings-watch", "Rur tailings watch", "aoi", "Rur valley, Germany",
            (6.45, 50.72), (6.40, 50.69, 6.50, 50.75), "mining",
            ["erosion", "structure"], "weekly", 3, value=64_000_000, population=80,
            assets=[{"id": "T01", "name": "Tailings dam north cell", "valueEur": 64_000_000, "population": 80, "critical": True, "groundM": 8.0}],
        ),
    ]
    plans = [
        _plan(scopes[0], digest="instant", budget=2500),
        _plan(scopes[1], digest="daily", budget=1200),
        _plan(scopes[2], digest="weekly", budget=800),
        _plan(scopes[3], digest="instant", budget=1500),
        _plan(scopes[4], digest="weekly", budget=400),
        _plan(scopes[5], digest="daily", budget=2000),
    ]
    for scope in scopes:
        store.save_scope(scope)
    for plan in plans:
        store.save_plan(plan)

    baselines = [
        _baseline(scopes[0].id, "change_fraction", [0.03, 0.04, 0.03, 0.05, 0.04, 0.06, 0.05, 0.04]),
        _baseline(scopes[1].id, "change_fraction", [0.02, 0.03, 0.02, 0.04, 0.03, 0.02]),
        _baseline(scopes[2].id, "change_fraction", [0.01, 0.02, 0.02, 0.03, 0.02, 0.02]),
        _baseline(scopes[3].id, "change_fraction", [0.02, 0.03, 0.03, 0.02, 0.04]),
        _baseline(scopes[4].id, "ndvi", [0.74, 0.72, 0.75, 0.73, 0.71, 0.72, 0.70], season="summer"),
        _baseline(scopes[5].id, "change_fraction", [0.01, 0.01, 0.02, 0.01, 0.02]),
    ]
    for baseline in baselines:
        store.save_baseline(baseline)

    acquisitions = []
    for scope, hours in zip(scopes, [6, 20, 30, 10, 38, 190]):
        acq = store.save_acquisition(
            Acquisition(
                id=f"acq-{scope.id}",
                scope_id=scope.id,
                source="sentinel-2" if scope.id != "scope-tailings-watch" else "sentinel-1",
                scheduled_for=_ago(hours),
                status="received" if scope.id != "scope-tailings-watch" else "failed",
                cloud_forecast=0.12 if scope.id != "scope-tailings-watch" else 0.42,
                cost_eur=0.0 if scope.id != "scope-tailings-watch" else 220.0,
                priority=scope.priority,
                idempotency_key=f"{scope.id}:seed:received",
                bbox=scope.bbox,
                resolution_m=10.0,
                scene_id=f"SCENE-{scope.id[-6:].upper()}",
                received_at=_ago(hours) if scope.id != "scope-tailings-watch" else None,
                readiness=0.91 if scope.id != "scope-tailings-watch" else 0.21,
                blind_spot_reason=None if scope.id != "scope-tailings-watch" else "cloud cover and failed tasking",
                provenance={"imagery": "simulated demo pack", "dryRun": True},
            )
        )
        acquisitions.append(acq)
        if scope.status == "active":
            planned = store.save_acquisition(
                Acquisition(
                    id=f"acq-next-{scope.id}",
                    scope_id=scope.id,
                    source="sentinel-2",
                    scheduled_for=_ahead(12 if scope.cadence == "12h" else 24 if scope.cadence == "daily" else 168),
                    status="planned",
                    cloud_forecast=0.18,
                    cost_eur=0.0,
                    priority=scope.priority,
                    idempotency_key=f"{scope.id}:seed:next",
                    bbox=scope.bbox,
                    resolution_m=10.0,
                    provenance={"planned": True},
                )
            )
            acquisitions.append(planned)

    forecasts = [
        Forecast(id="fc-ahr-flood", region="Ahrweiler, Germany", issued_at=_ago(2), valid_from=_ago(1), valid_to=_ahead(30), hazard="flood", probability=0.78, rainfall_mm=62, river_level_m=3.4, uncertainty=0.18, confidence=0.82, metadata={"cloudCover": 0.35}),
        Forecast(id="fc-rur-flood", region="Rur valley, Germany", issued_at=_ago(3), valid_from=_ago(1), valid_to=_ahead(28), hazard="flood", probability=0.62, rainfall_mm=44, river_level_m=2.7, uncertainty=0.24, confidence=0.76, metadata={"cloudCover": 0.28}),
        Forecast(id="fc-eifel-fire", region="Eifel, Germany", issued_at=_ago(4), valid_from=_ago(1), valid_to=_ahead(36), hazard="wildfire", probability=0.55, wind_kmh=38, uncertainty=0.3, confidence=0.7, metadata={"cloudCover": 0.1}),
        Forecast(id="fc-cologne-storm", region="Cologne, Germany", issued_at=_ago(3), valid_from=_ago(1), valid_to=_ahead(24), hazard="storm", probability=0.36, wind_kmh=52, uncertainty=0.26, confidence=0.74, metadata={"cloudCover": 0.4}),
        Forecast(id="fc-dernau-frost", region="Dernau, Germany", issued_at=_ago(5), valid_from=_ago(1), valid_to=_ahead(40), hazard="freeze", probability=0.31, uncertainty=0.3, confidence=0.7, metadata={"cloudCover": 0.2}),
    ]
    for forecast in forecasts:
        store.save_forecast(forecast)

    incidents = [
        _incident("INC-AHR-01", scopes[0], "Flood impacts along the Ahr corridor", "red", "investigating", ["ALT-1001", "ALT-1002"], "A. Weber"),
        _incident("INC-AHR-02", scopes[0], "Levee erosion near Heimersheim", "orange", "open", ["ALT-1003"], "M. Keller"),
        _incident("INC-RUR-01", scopes[1], "Vegetation and access change on the Rur corridor", "orange", "open", ["ALT-1004"], "M. Keller"),
        _incident("INC-EIF-01", scopes[3], "Burn scar expansion on the Eifel ridge", "red", "investigating", ["ALT-1008"], "S. Okafor"),
        _incident("INC-TAI-01", scopes[5], "Tailings dam surface change", "red", "open", ["ALT-1012"], "A. Weber"),
    ]
    for incident in incidents:
        store.save_incident(incident)

    alert_specs = [
        ("ALT-1001", 0, "Flood edge reaches the care campus", "The flood edge crossed the Bad Neuenahr care campus footprint. Access is flooded; 1,800 people within 700 m. Validate and consider Team 1.", "red", "flood", 0.91, 0.18, 0.05, 7.104, 50.548, "new", None, "INC-AHR-01", "Bad Neuenahr care campus", 6_200_000, 1800, "flooded", 1.2, "A. Weber", 0.91),
        ("ALT-1002", 0, "Substation access road flooded", "Primary access to the Heppingen substation is under water. Power asset remains dry; response is restricted.", "orange", "flood", 0.86, 0.12, 0.05, 7.082, 50.541, "assigned", "M. Keller", "INC-AHR-01", "Heppingen substation", 8_400_000, 640, "restricted", 2.8, None, 0.86),
        ("ALT-1003", 0, "Levee erosion near Heimersheim", "A persistent 0.09 change fraction along the levee toe; two consecutive observations confirm the trend.", "orange", "erosion", 0.79, 0.09, 0.03, 7.140, 50.549, "investigating", "M. Keller", "INC-AHR-02", "Levee sector 4", 4_200_000, 900, "blocked", 5.0, "A. Weber", 0.79),
        ("ALT-1004", 1, "Vegetation encroachment on feeder 2", "Canopy change within the Rur utility corridor. No outage reported; inspection advised.", "orange", "vegetation", 0.74, 0.11, 0.04, 6.421, 50.761, "new", None, "INC-RUR-01", "Rur feeder 2", 1_800_000, 300, "slow", 2.2, None, 0.74),
        ("ALT-1005", 1, "Pump station corridor change", "A 0.14 change fraction near the Rur pump station; SAR agrees with the optical observation.", "red", "structure", 0.88, 0.14, 0.04, 6.426, 50.758, "acknowledged", "A. Weber", None, "Rur pump station", 7_100_000, 300, "restricted", 4.6, "A. Weber", 0.88),
        ("ALT-1006", 2, "New construction footprint in Ehrenfeld", "A new foundation appears across two observations. This is expected construction; resolved by the project office.", "yellow", "construction", 0.67, 0.07, 0.02, 6.906, 50.936, "resolved", "S. Okafor", None, "Ehrenfeld rail yard", 12_000_000, 400, "clear", 26.0, "S. Okafor", 0.67),
        ("ALT-1007", 2, "Stockpile expansion outside the fence", "Change extends beyond the permitted footprint. Assigned for a site visit.", "orange", "construction", 0.71, 0.09, 0.02, 6.912, 50.931, "assigned", "M. Keller", None, "Braunsfeld depot", 2_500_000, 250, "clear", 30.0, None, 0.71),
        ("ALT-1008", 3, "Burn scar expands east", "The burn perimeter advanced 1.2 km east. Two structures are inside the new perimeter; one is a watch item.", "red", "wildfire", 0.89, 0.21, 0.03, 6.428, 50.592, "investigating", "S. Okafor", "INC-EIF-01", "Vogelsang forest block", 4_400_000, 120, "restricted", 3.4, "S. Okafor", 0.89),
        ("ALT-1009", 3, "Smoke plume read as change", "The apparent change is a smoke plume; the analyst rejected it. Recorded as a false positive.", "yellow", "wildfire", 0.61, 0.08, 0.03, 6.415, 50.586, "dismissed", "S. Okafor", None, "Eifel ridge", 200_000, 20, "clear", 8.2, "S. Okafor", 0.61, "cloud_shadow"),
        ("ALT-1010", 4, "NDVI drop in the Dernau terraces", "NDVI fell 0.11 below the seasonal baseline. Could be drought stress or disease; agronomist review required.", "orange", "vegetation", 0.76, 0.13, 0.02, 7.052, 50.531, "new", None, None, "Dernau vineyard terraces", 2_800_000, 180, "slow", 1.8, None, 0.76),
        ("ALT-1011", 4, "Field boundary change is a harvest", "The boundary change matches the harvest calendar. Dismissed as no action.", "yellow", "vegetation", 0.58, 0.06, 0.02, 7.049, 50.529, "dismissed", "M. Keller", None, "Dernau field 3", 300_000, 10, "clear", 19.0, None, 0.58, "no_action"),
        ("ALT-1012", 5, "Tailings dam surface change", "A 0.16 surface change appears inside the tailings footprint. Sentinel-1 is the only reliable source; geotechnical review required.", "red", "erosion", 0.84, 0.16, 0.02, 6.451, 50.721, "new", None, "INC-TAI-01", "Tailings dam north cell", 64_000_000, 80, "restricted", 2.6, None, 0.84),
        ("ALT-1013", 5, "Haul road change resolved", "The haul road realignment matches the approved plan. Resolved.", "orange", "construction", 0.72, 0.10, 0.02, 6.447, 50.718, "resolved", "A. Weber", None, "Tailings haul road", 900_000, 40, "clear", 22.0, "A. Weber", 0.72),
        ("ALT-1014", 1, "Duplicate vegetation alert", "Same footprint as ALT-1004, one hour later. Dismissed as duplicate.", "yellow", "vegetation", 0.69, 0.10, 0.04, 6.4215, 50.7612, "dismissed", "M. Keller", None, "Rur feeder 2", 1_800_000, 300, "slow", 1.4, None, 0.69, "duplicate"),
    ]
    alerts: list[Alert] = []
    for spec in alert_specs:
        (aid, scope_index, title, summary, severity, ctype, conf, observed, baseline, lon, lat, status, assignee, incident_id, asset, value, population, access, created_hours, validator, lead, *rest) = spec
        dismissed = rest[0] if rest else None
        alert = _alert(
            alert_id=aid,
            scope=scopes[scope_index],
            title=title,
            summary=summary,
            severity=severity,
            change_type=ctype,
            confidence=conf,
            observed=observed,
            baseline=baseline,
            lon=lon,
            lat=lat,
            status=status,
            assignee=assignee,
            incident_id=incident_id,
            asset=asset,
            value=value,
            population=population,
            access=access,
            created_hours_ago=created_hours,
            dismissed_reason=dismissed,
            validated=bool(validator),
            lead_time=lead,
        )
        if validator:
            alert.validated_by = validator
            alert.validation_count = 3
        if status == "acknowledged":
            alert.acknowledged_at = _ago(max(0.2, created_hours - 0.3))
        if status == "resolved":
            alert.resolved_at = _ago(max(0.1, created_hours - 1))
        if status == "dismissed":
            alert.dismissed_reason = dismissed or "other"
            alert.dismissal_note = "Demo dismissal with a visible reason."
        alerts.append(store.save_alert(alert))

    # Historical resolved alerts: the pilot measured them, the inbox keeps the audit trail.
    for index in range(10):
        scope = scopes[index % 5]
        historical = _alert(
            alert_id=f"ALT-2{index:03d}",
            scope=scope,
            title=f"Resolved watch item {index + 1}",
            summary="A historical alert closed after analyst review. Kept for precision and audit.",
            severity="orange" if index % 3 else "red",
            change_type=["flood", "construction", "vegetation", "erosion", "wildfire"][index % 5],
            confidence=0.82 - index * 0.01,
            observed=0.12,
            baseline=0.03,
            lon=scope.center[0] + 0.002 * (index % 3),
            lat=scope.center[1] - 0.002 * (index % 2),
            status="resolved",
            assignee="A. Weber",
            incident_id=None,
            asset="Historical asset",
            value=1_200_000,
            population=120,
            access="clear",
            created_hours_ago=40 + index * 9,
            validated=True,
            lead_time=12.0 + index,
        )
        alerts.append(store.save_alert(historical))

    # Link alerts to their incidents (already set above, but keep incident lists consistent).
    for incident in incidents:
        linked = [a for a in alerts if a.incident_id == incident.id]
        incident.alert_ids = [a.id for a in linked] or incident.alert_ids
        store.save_incident(incident)

    preferences = TenantPreferences(
        tenant=TENANT,
        channels=["email", "slack", "teams"],
        quiet_hours=(22, 7),
        digest="instant",
        language="en",
        alert_budget_per_day=8,
        recipients=[
            {"name": "Ops desk", "email": "ops@example.com", "channels": ["email", "slack", "teams"]},
            {"name": "Claims lead", "email": "claims@example.com", "channels": ["email"]},
            {"name": "On-call", "phone": "+000000000", "channels": ["sms"]},
        ],
        escalation_minutes=30,
    )
    store.save_preferences(preferences)

    store.save_model(ModelEntry(name="gr-changenet", version="1.4.2", status="deployed", metrics={"precision": 0.91, "recall": 0.87}, rollback_to="1.3.9", notes="Pinned on every alert"))
    store.save_model(ModelEntry(name="gr-changenet-shadow", version="1.5.0", status="shadow", metrics={"precision": 0.93, "recall": 0.88}, rollback_to="1.4.2", notes="Shadow candidate; not customer-visible"))
    store.save_model(ModelEntry(name="gr-damage-head", version="1.0", status="deployed", metrics={"precision": 0.86, "recall": 0.81}, notes="Damage likelihood head"))

    for index, alert in enumerate(alerts):
        store.add_cost(CostEntry(id=f"cost-imagery-{index}", tenant=TENANT, scope_id=alert.scope_id, kind="imagery", amount_eur=0.0 if index < 9 else 60.0))
        store.add_cost(CostEntry(id=f"cost-analyst-{index}", tenant=TENANT, scope_id=alert.scope_id, kind="analyst", amount_eur=18.0))

    for index, alert in enumerate(alerts[:5]):
        notification = Notification(
            id=f"NOT-{index}",
            tenant=TENANT,
            alert_id=alert.id,
            channel=["email", "slack", "teams", "email", "sms"][index],
            recipient=["ops@example.com", "ops@example.com", "ops@example.com", "claims@example.com", "+000000000"][index],
            subject=alert.title,
            body=alert.summary,
            status="sent" if index != 4 else "failed",
            attempts=1 if index != 4 else 2,
            sent_at=_ago(0.4) if index != 4 else None,
            next_attempt_at=_ahead(0.2) if index == 4 else None,
            error="demo transport timeout" if index == 4 else None,
            payload={"demo": True},
        )
        store.save_notification(notification)

    for scope_index in (0, 1, 2, 3, 4):
        for n in range(3 if scope_index == 0 else 1):
            store.add_validation(ValidationRecord(scope_id=scopes[scope_index].id, analyst="A. Weber", alert_id=alerts[scope_index].id, decision="validated"))
    return {"scopes": scopes, "plans": plans, "alerts": alerts, "incidents": incidents, "forecasts": forecasts, "acquisitions": acquisitions}


def build_demo() -> dict:
    store = ProactiveStore(":memory:")
    seed = seed_demo(store)
    engine = ProactiveEngine(store)
    forecasts = store.list_forecasts()
    dashboard = engine.dashboard(TENANT)
    watch = engine.watch(TENANT, forecasts)
    pilot = engine.pilot_report(TENANT)
    digest = alert_ops.digest(store, TENANT)
    coverage_rows = watch["coverage"]
    payload = {
        "generatedAt": now_iso(),
        "tenant": TENANT,
        "mode": "proactive",
        "disclaimer": "Demo monitoring data. Algorithms and lifecycle are real; the scopes, alerts and metrics are seeded for the showcase.",
        "shadowMode": False,
        "scopes": [scope.to_dict() for scope in seed["scopes"]],
        "plans": [plan.to_dict() for plan in seed["plans"]],
        "alerts": [alert.to_dict() for alert in seed["alerts"]],
        "incidents": [incident.to_dict() for incident in seed["incidents"]],
        "forecasts": [forecast.to_dict() for forecast in forecasts],
        "acquisitions": [acquisition.to_dict() for acquisition in seed["acquisitions"]],
        "baselines": [baseline.to_dict() for scope in seed["scopes"] for baseline in store.list_baselines(scope.id)],
        "preferences": preferences_payload(store.get_preferences(TENANT)),
        "models": [model.to_dict() for model in store.list_models()],
        "dashboard": dashboard,
        "watch": watch,
        "pilot": pilot,
        "digest": digest,
        "quality": alert_quality(store, TENANT),
        "governance": governance_snapshot(store, TENANT),
        "coverage": coverage_rows,
        "calendar": {scope.id: calendar(store, scope.id) for scope in seed["scopes"]},
        "notifications": [
            {"id": n.id, "alertId": n.alert_id, "channel": n.channel, "recipient": n.recipient, "status": n.status, "attempts": n.attempts, "nextAttemptAt": n.next_attempt_at, "error": n.error}
            for n in store.list_notifications(tenant=TENANT)
        ],
        "costs": {
            "summary": cost_report(store, TENANT, days=30),
            "byScope": [
                {"scopeId": scope.id, "name": scope.name, "totalEur": store.total_cost(TENANT, scope_id=scope.id)} for scope in seed["scopes"]
            ],
        },
        "blindSpots": watch["blindSpots"],
        "freshness": watch["freshness"],
    }
    kill = KillSwitch(store)
    payload["killSwitch"] = kill.active(TENANT)
    store.close()
    return payload


def write_demo(path: str | Path = "web/public/data/proactive.json") -> dict:
    payload = build_demo()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(destination), "scopes": len(payload["scopes"]), "alerts": len(payload["alerts"]), "bytes": destination.stat().st_size}


if __name__ == "__main__":
    print(json.dumps(write_demo(), indent=2))
