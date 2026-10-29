"""Pilot measurement: baseline, accuracy, false positives, time saved.

The numbers in the bundled pack are synthetic pilot data, clearly labelled.  The
functions are the same ones that would consume real adjuster-confirmed outcomes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .config import PILOT


def _event(event_id: str, region: str, day: str, claims: int, detected: int, confirmed: int, fp: int, minutes: int, analyst_minutes: int) -> dict:
    return {
        "id": event_id,
        "region": region,
        "date": day,
        "claims": claims,
        "detected": detected,
        "confirmed": confirmed,
        "falsePositives": fp,
        "assessmentMinutes": minutes,
        "baselineMinutes": analyst_minutes,
        "analyst": "A. Weber",
        "modelVersion": "gr-changenet-1.4.2",
    }


def baseline_event(event_id: str = "baseline-01", region: str = "Ahrweiler", claims: int = 18) -> dict:
    """Manual baseline: analyst scans tiles and writes the notice by hand."""
    return {
        "id": event_id,
        "region": region,
        "date": "2021-07-15",
        "claims": claims,
        "detected": 18,
        "confirmed": 16,
        "falsePositives": 2,
        "assessmentMinutes": PILOT.baseline_minutes,
        "baselineMinutes": PILOT.baseline_minutes,
        "analyst": "manual",
        "modelVersion": "none",
    }


def default_pilot_history() -> list[dict]:
    return [
        baseline_event(),
        _event("pilot-01", "Ahrweiler", "2026-03-04", 22, 22, 19, 3, 44, 1180),
        _event("pilot-02", "Rur valley", "2026-03-19", 16, 16, 14, 2, 39, 1090),
        _event("pilot-03", "Ahrweiler", "2026-04-02", 27, 27, 24, 3, 47, 1310),
        _event("pilot-04", "Eifel north", "2026-04-21", 13, 13, 12, 1, 34, 940),
        _event("pilot-05", "Ahrweiler", "2026-05-06", 31, 31, 29, 2, 41, 1460),
        _event("pilot-06", "Rur valley", "2026-05-28", 19, 19, 18, 1, 36, 1120),
    ]


def accuracy(event: dict) -> dict:
    denom = max(1, event["detected"])
    precision = event["confirmed"] / denom
    recall = event["confirmed"] / max(1, event["claims"])
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "falsePositiveRate": round(event["falsePositives"] / denom, 3),
    }


def false_positive_log() -> list[dict]:
    reasons = [
        ("FP-01", "dark roof + wet pavement read as structural damage", "roof reflection", 0.91, "rejected", "Ahrweiler Altstadt"),
        ("FP-02", "deep shadow along a retaining wall", "shadow", 0.84, "rejected", "Bad Neuenahr Kurpark"),
        ("FP-03", "silt deposits on a field", "sediment", 0.73, "flagged", "Heppingen south"),
        ("FP-04", "parked vehicles under a bridge", "occlusion", 0.68, "rejected", "Heimersheim bridge"),
        ("FP-05", "new roof colour after repair", "seasonal", 0.62, "rejected", "Bachem"),
        ("FP-06", "greenhouse plastic sheeting", "material", 0.58, "rejected", "Gimmigen"),
    ]
    return [
        {
            "id": fpid,
            "reason": reason,
            "category": category,
            "confidence": confidence,
            "review": review,
            "location": location,
            "modelVersion": "gr-changenet-1.4.2",
        }
        for fpid, reason, category, confidence, review, location in reasons
    ]


def build_pilot_dashboard(history: list[dict] | None = None) -> dict:
    history = history or default_pilot_history()
    pilot = [e for e in history if e["modelVersion"] != "none"]
    total_detected = sum(e["detected"] for e in pilot)
    total_confirmed = sum(e["confirmed"] for e in pilot)
    total_fp = sum(e["falsePositives"] for e in pilot)
    total_claims = sum(e["claims"] for e in pilot)
    minutes_saved = sum(e["baselineMinutes"] - e["assessmentMinutes"] for e in pilot)
    accuracy_series = [
        {
            "date": e["date"],
            "precision": accuracy(e)["precision"],
            "recall": accuracy(e)["recall"],
            "falsePositives": e["falsePositives"],
        }
        for e in pilot
    ]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Synthetic pilot data for the demo. Replace with adjuster-confirmed outcomes before making claims.",
        "summary": {
            "events": len(pilot),
            "claims": total_claims,
            "detected": total_detected,
            "confirmed": total_confirmed,
            "falsePositives": total_fp,
            "precision": round(total_confirmed / max(1, total_detected), 3),
            "recall": round(total_confirmed / max(1, total_claims), 3),
            "analystHoursSaved": round(minutes_saved / 60, 1),
            "avgAssessmentMinutes": round(sum(e["assessmentMinutes"] for e in pilot) / max(1, len(pilot))),
            "baselineMinutes": PILOT.baseline_minutes,
            "accuracyTrend": accuracy_series,
        },
        "history": history,
        "falsePositiveLog": false_positive_log(),
        "byReason": _by_reason(false_positive_log()),
        "timeToAssessment": {
            "manualMinutes": PILOT.baseline_minutes,
            "georesponseMinutes": PILOT.assessment_minutes,
            "savedMinutes": PILOT.baseline_minutes - PILOT.assessment_minutes,
            "savedPct": round((1 - PILOT.assessment_minutes / PILOT.baseline_minutes) * 100, 1),
        },
        "cost": {
            "analystHourlyEur": PILOT.analyst_hourly_eur,
            "savedEur": round(minutes_saved / 60 * PILOT.analyst_hourly_eur),
        },
    }


def _by_reason(log: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for item in log:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def precision_recall_report(history: list[dict] | None = None) -> dict:
    history = history or default_pilot_history()
    per_event = [{"id": e["id"], "region": e["region"], "date": e["date"], **accuracy(e)} for e in history if e["modelVersion"] != "none"]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modelVersion": "gr-changenet-1.4.2",
        "perEvent": per_event,
        "note": "Precision = confirmed / detected. Recall = confirmed / claims. Adjuster-confirmed only.",
    }


def pilot_offer() -> dict:
    today = date.today()
    end = today + timedelta(days=90)
    return {
        "title": "GeoResponse pilot in 90 days",
        "start": today.isoformat(),
        "end": end.isoformat(),
        "scope": "One insurer, one storm/flood event, one region. AI assessment runs in parallel with the manual process.",
        "deliverables": [
            "Imagery pipeline for the customer's event",
            "Ranked site list with confidence and value at risk",
            "Claims first-notice assessment (human-signed)",
            "Accuracy, false-positive and time-saved report",
            "On-site or private-cloud deployment option",
        ],
        "successMeasures": [
            "Time to assessment: days → hours",
            "Detection precision ≥ 0.85 against adjuster-confirmed damage",
            "Analyst hours saved ≥ 40%",
            "Zero automated claim approvals",
        ],
        "commercial": "Fixed pilot fee credited against the annual subscription.",
    }
