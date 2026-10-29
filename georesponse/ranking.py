"""Ranking engine.

Score = weighted sum of normalised, observable factors:

* change extent       - how much changed
* confidence          - model confidence, after cloud penalty
* value at risk       - insured / asset value
* access risk         - blocked or flooded routes
* population          - people affected

Every score carries its contributions so the UI can show *why* a site ranks.
Rejected sites are removed and the remaining list re-ranks deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_WEIGHTS


@dataclass
class RankedSite:
    site: dict
    score: float
    rank: int
    contributions: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "id": self.site["id"],
            "rank": self.rank,
            "score": round(self.score, 4),
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
        }


def _norm(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-9:
        return [0.5 for _ in values]
    return [(v - low) / (high - low) for v in values]


def access_factor(status: str) -> float:
    return {
        "blocked": 1.0,
        "flooded": 0.92,
        "restricted": 0.72,
        "debris": 0.8,
        "slow": 0.55,
        "clear": 0.18,
    }.get(status.lower(), 0.5)


def rank_sites(
    sites: list[dict],
    *,
    weights: dict[str, float] | None = None,
    exclude: set[str] | None = None,
) -> tuple[list[RankedSite], list[str]]:
    """Return ranked sites plus warnings about the inputs."""
    weights = dict(weights or DEFAULT_WEIGHTS)
    exclude = exclude or set()
    warnings: list[str] = []
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("ranking weights must sum to a positive value")
    weights = {k: v / total for k, v in weights.items()}

    candidates = [s for s in sites if s["id"] not in exclude]
    if not candidates:
        return [], ["no candidate sites after exclusions"]

    extents = _norm([float(s.get("changeExtentM2", 0)) for s in candidates])
    values = _norm([float(s.get("valueEur", 0)) for s in candidates])
    populations = _norm([float(s.get("population", 0)) for s in candidates])

    ranked: list[RankedSite] = []
    for i, site in enumerate(candidates):
        confidence = float(site.get("confidence", 0.5))
        access = access_factor(str(site.get("accessStatus", "clear")))
        contributions = {
            "extent": extents[i] * weights["extent"],
            "confidence": confidence * weights["confidence"],
            "value": values[i] * weights["value"],
            "access": access * weights["access"],
            "population": populations[i] * weights["population"],
        }
        score = sum(contributions.values())
        if confidence < 0.5:
            warnings.append(f"{site['id']}: low confidence ({confidence:.0%})")
        if site.get("cloud", 0) > 0.3:
            warnings.append(f"{site['id']}: cloud cover may hide change")
        ranked.append(RankedSite(site=site, score=score, rank=0, contributions=contributions))

    ranked.sort(key=lambda r: (-r.score, r.site["id"]))
    for index, item in enumerate(ranked, start=1):
        item.rank = index
    return ranked, warnings


def coverage_plan(ranked: list[RankedSite], teams: int = 3) -> list[dict]:
    """Greedy coverage: assign teams to the top distinct, highest-ranked sites."""
    return [
        {
            "team": f"Team {i + 1}",
            "siteId": item.site["id"],
            "siteName": item.site["name"],
            "score": round(item.score, 4),
        }
        for i, item in enumerate(ranked[:teams])
    ]


def rank_disclosure(ranked: list[RankedSite]) -> list[dict]:
    return [
        {
            "id": item.site["id"],
            "rank": item.rank,
            "score": round(item.score, 3),
            "confidence": item.site.get("confidence"),
            "severity": item.site.get("severity"),
            "why": {
                "extentM2": item.site.get("changeExtentM2"),
                "insuredValueEur": item.site.get("valueEur"),
                "population": item.site.get("population"),
                "access": item.site.get("accessStatus"),
            },
            "contributions": {k: round(v, 3) for k, v in item.contributions.items()},
        }
        for item in ranked
    ]
