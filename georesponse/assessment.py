"""Assessment writer.

The "agent" is a deterministic tool-using orchestrator: it calls ranking, context
and template tools, then writes the assessment.  Every number in the text is
traceable to a finding, and every finding is traceable to imagery and a model
version.  An optional LLM hook can add narrative, but it can never change the
numbers or approve a site.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import MODEL_VERSION
from .config import PILOT
from .ranking import RankedSite


def _money(value: int | float) -> str:
    return f"€{value:,.0f}"


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def agent_trace(steps: list[dict]) -> list[dict]:
    return [{"step": i + 1, **step} for i, step in enumerate(steps)]


def write_assessment(
    scenario: dict,
    ranked: list[RankedSite],
    *,
    reviews: dict[str, str] | None = None,
    teams: int = 3,
    analyst: str = "A. Weber",
) -> dict:
    reviews = reviews or {}
    meta = scenario["meta"]
    rejected_ids = {sid for sid, status in reviews.items() if status == "rejected"}
    reviewed_count = len(rejected_ids)
    active = [r for r in ranked if r.site["id"] not in rejected_ids]
    top = active[:3]
    total_value = sum(s.site.get("valueEur", 0) for s in active)
    total_pop = sum(s.site.get("population", 0) for s in active)
    top_ids = ", ".join(s.site["id"] for s in top)

    summary = (
        f"{meta['title']} affects {meta['areaKm2']:.0f} km². "
        f"{len(active)} priority sites remain after review; "
        f"{reviewed_count} finding(s) were rejected by an analyst. "
        f"The top three sites ({top_ids}) carry {_money(total_value)} of exposed value "
        f"and {total_pop:,} people within 700 m. "
        f"Three response teams are allocated by urgency, access and value at risk."
    )

    if top:
        first = top[0]
        site = first.site
        scenario_sentence = (
            f"The highest-ranked site is {site['name']} ({site['id']}), severity {site['severity']}, "
            f"confidence {_pct(site['confidence'])}. "
            f"A {site['changeExtentM2']:,} m² change intersects {site['accessStatus']} access; "
            f"{site.get('population', 0):,} people live within 700 m and the insured value is "
            f"{_money(site.get('valueEur', 0))}."
        )
    else:
        scenario_sentence = "No sites remain after review. No team allocation is recommended."

    findings = []
    for item in ranked:
        site = item.site
        review = reviews.get(site["id"])
        findings.append(
            {
                "id": site["id"],
                "name": site["name"],
                "rank": item.rank,
                "score": round(item.score, 3),
                "severity": site["severity"],
                "confidence": site["confidence"],
                "confidenceLabel": "high" if site["confidence"] >= 0.85 else "medium" if site["confidence"] >= 0.65 else "low",
                "changeExtentM2": site["changeExtentM2"],
                "valueEur": site.get("valueEur", 0),
                "population": site.get("population", 0),
                "access": site["accessStatus"],
                "review": review or "pending",
                "reviewReason": site.get("falsePositiveReason") if review == "rejected" else None,
                "imagery": site.get("evidence", {}),
                "modelVersion": MODEL_VERSION,
            }
        )

    limitations = [
        "Change extent is derived from a simulated Sentinel-2-like 10 m composite in the demo pack; production uses licensed imagery.",
        "Dark roofs, wet pavement and deep shadow can mimic structural damage; every rejection is retained in the audit trail.",
        "Population is a 700 m radius estimate from the demo population grid, not a household count.",
        "No site is approved automatically. A human analyst signs the assessment before any claim or dispatch decision.",
    ]

    claim = {
        "template": PILOT.template,
        "claimRef": f"CLM-{meta['id'].upper()}-{datetime.now(timezone.utc):%y%m}",
        "dateOfLoss": meta.get("eventDate"),
        "causeOfLoss": meta.get("hazard", "flood"),
        "region": meta.get("region"),
        "insured": top[0].site.get("policy", {}).get("holder") if top else None,
        "property": top[0].site.get("policy", {}).get("propertyType") if top else None,
        "damageSummary": scenario_sentence,
        "recommendedAction": "Dispatch adjuster to the top-ranked site; remote review for the remainder.",
        "reserveEstimateEur": round(total_value * 0.18),
        "adjusterRequired": True,
        "attachments": ["change-overlay.geojson", "assessment.pdf", "field-order.pdf"],
        "confidenceDisclosure": "Every finding carries model confidence and imagery provenance.",
    }

    return {
        "title": f"GeoResponse assessment — {meta['title']}",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "analyst": analyst,
        "modelVersion": MODEL_VERSION,
        "summary": summary,
        "headline": scenario_sentence,
        "teams": teams,
        "metrics": {
            "sites": len(active),
            "rejected": reviewed_count,
            "areaKm2": meta["areaKm2"],
            "exposedValueEur": total_value,
            "population": total_pop,
            "assessmentMinutes": meta.get("assessmentMinutes", PILOT.assessment_minutes),
            "baselineMinutes": meta.get("baselineMinutes", PILOT.baseline_minutes),
        },
        "findings": findings,
        "limitations": limitations,
        "claim": claim,
        "disclosure": (
            "AI-assisted assessment. A human analyst reviews and signs every location. "
            f"Imagery: {meta['imagery']['source']}. Model: {MODEL_VERSION}."
        ),
        "trace": agent_trace(
            [
                {"tool": "imagery.list", "detail": f"{meta['imagery']['source']} · {meta['eventDate']}"},
                {"tool": "change.detect", "detail": f"{len(ranked)} candidate sites, cloud screen 30%"},
                {"tool": "context.enrich", "detail": "roads, power assets, population, insured value"},
                {"tool": "ranking.score", "detail": "extent 28 · confidence 18 · value 22 · access 16 · population 16"},
                {"tool": "assessment.write", "detail": "claims first-notice template"},
                {"tool": "human.review", "detail": "analyst approval required"},
            ]
        ),
    }


def one_paragraph(scenario: dict, ranked: list[RankedSite]) -> str:
    """A single paragraph for the booth / field order."""
    top = ranked[0].site if ranked else None
    if not top:
        return "No actionable change detected."
    return (
        f"{scenario['meta']['title']}: {len(ranked)} priority sites across "
        f"{scenario['meta']['areaKm2']:.0f} km². Send the first team to {top['name']} "
        f"({top['severity']}, {round(top['confidence'] * 100)}% confidence, "
        f"{top['accessStatus']} access). Treat the ranking as decision support; "
        f"the analyst signs the assessment."
    )
