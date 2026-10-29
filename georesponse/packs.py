"""Sector packs: agriculture and mining beyond the first insurer pilot."""

from __future__ import annotations

PACKS = {
    "agriculture": {
        "id": "agriculture",
        "title": "Agriculture pack",
        "hazard": "vegetation",
        "buyers": ["crop insurers", "agri cooperatives", "farm lenders"],
        "changeTypes": [
            "NDVI delta over the season",
            "field boundary change",
            "flooded or lodged crop",
            "hail / storm damage",
        ],
        "signals": ["Sentinel-2 10 m", "Sentinel-1 SAR", "customer yield records", "field polygons"],
        "firstWorkflow": "Flag fields whose NDVI delta is outside the parcel baseline; rank by insured value and access.",
        "metrics": ["hectares assessed", "detection precision", "adjuster hours saved", "false alarms by crop"],
        "guardrails": ["Do not infer yield from imagery alone", "Human agronomist review", "Weather data is context, not proof"],
    },
    "mining": {
        "id": "mining",
        "title": "Mining pack",
        "hazard": "operational",
        "buyers": ["mine operators", "tailings insurers", "regulators"],
        "changeTypes": [
            "tailings dam surface change",
            "haul-road and pit expansion",
            "vegetation encroachment",
            "equipment and stockpile change",
        ],
        "signals": ["high-resolution commercial imagery", "Sentinel-1 InSAR", "survey vectors", "asset register"],
        "firstWorkflow": "Weekly corridor watch; alert on change inside the tailings footprint; rank by consequence and access.",
        "metrics": ["inspection coverage", "alert precision", "time to inspection", "false alarms"],
        "guardrails": ["Not a safety certification", "Geotechnical engineer review", "Regulator data terms apply"],
    },
}


def build_pack(name: str) -> dict:
    if name not in PACKS:
        raise KeyError(f"unknown pack: {name}")
    pack = dict(PACKS[name])
    pack["pilotOffer"] = f"90-day {name} pilot: one site, one change type, parallel to the current inspection process."
    pack["integration"] = ["CSV / GeoJSON", "Esri ArcGIS", "IBM Maximo", "SAP PM"]
    return pack


def all_packs() -> list[dict]:
    return [build_pack(name) for name in PACKS]


def partner_programme() -> dict:
    return {
        "title": "Partner programme",
        "partners": [
            "Reinsurers: portfolio-level event triage",
            "Imagery providers: licensed high-resolution tasking",
            "Survey firms: ground-truth and adjuster capacity",
            "NPU / edge vendors: on-site inference appliances",
        ],
        "terms": "Referral fee or revenue share, no exclusive territory, joint pilot governance.",
        "guardrails": "Partner data stays tenant-scoped; no cross-customer model training without written consent.",
    }


def government_framework() -> dict:
    return {
        "title": "Government / emergency management framework",
        "scope": "Event triage for civil protection, not automated decisions about people.",
        "procurement": ["framework agreement", "data-processing annex", "security questionnaire", "pilot acceptance tests"],
        "deployment": ["on-premise", "sovereign cloud", "air-gapped after imagery delivery"],
        "obligations": [
            "Human review before any field dispatch",
            "Publish provenance for every map",
            "Retention schedule per event",
            "Accessibility and language requirements",
            "No facial recognition, no live surveillance",
        ],
    }
