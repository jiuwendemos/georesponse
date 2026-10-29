"""Context enrichment: OSM-style layers, buildings, asset records and access.

The demo ships a deterministic context pack.  Production adapters accept the
same interfaces and read OSM/PostGIS/ArcGIS/claims extracts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .geo import BBox, metres_between


@dataclass
class Asset:
    id: str
    name: str
    kind: str
    lon: float
    lat: float
    value_eur: int = 0
    critical: bool = False
    meta: dict = field(default_factory=dict)


@dataclass
class ContextPack:
    roads: list[dict] = field(default_factory=list)
    buildings: list[dict] = field(default_factory=list)
    power: list[dict] = field(default_factory=list)
    landuse: list[dict] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    population: list[dict] = field(default_factory=list)

    def nearest_road(self, lon: float, lat: float) -> dict | None:
        best, best_d = None, 1e18
        for road in self.roads:
            for coord in road.get("coords", []):
                d = metres_between((lon, lat), coord)
                if d < best_d:
                    best, best_d = road, d
        if best is None:
            return None
        return {"name": best.get("name", "Unnamed road"), "distanceM": round(best_d), "class": best.get("class", "local")}

    def building_at(self, lon: float, lat: float) -> dict | None:
        point = Point(lon, lat)
        for building in self.buildings:
            if shape(building["geometry"]).buffer(0.00008).contains(point):
                return building.get("properties", {})
        return None

    def assets_near(self, lon: float, lat: float, radius_m: float = 550) -> list[Asset]:
        found = [(a, metres_between((lon, lat), (a.lon, a.lat))) for a in self.assets]
        return [a for a, d in sorted(found, key=lambda pair: pair[1]) if d <= radius_m]

    def population_near(self, lon: float, lat: float, radius_m: float = 700) -> int:
        total = 0
        for cell in self.population:
            d = metres_between((lon, lat), (cell["lon"], cell["lat"]))
            if d <= radius_m:
                total += int(cell.get("people", 0))
        return total


def load_context(path: str | Path) -> ContextPack:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ContextPack(
        roads=payload.get("roads", []),
        buildings=payload.get("buildings", []),
        power=payload.get("power", []),
        landuse=payload.get("landuse", []),
        assets=[Asset(**a) for a in payload.get("assets", [])],
        population=payload.get("population", []),
    )


def road_access_status(road: dict, flood_geometries: Iterable[dict]) -> str:
    """Classify access using the latest flood extent."""
    line = shape(road["geometry"])
    for geom in flood_geometries:
        if line.intersects(shape(geom)):
            overlap = line.intersection(shape(geom)).length
            if overlap > line.length * 0.35:
                return "blocked"
            if overlap > line.length * 0.08:
                return "flooded"
    if road.get("properties", {}).get("debris"):
        return "debris"
    return "clear"


def enrich_site(site: dict, context: ContextPack, flood: list[dict]) -> dict:
    lon, lat = site["lon"], site["lat"]
    road = context.nearest_road(lon, lat)
    building = context.building_at(lon, lat)
    assets = context.assets_near(lon, lat)
    people = context.population_near(lon, lat)
    status = site.get("accessStatus") or (road_access_status({"geometry": site["geometry"]}, flood) if site.get("geometry") else "clear")
    why = [
        {
            "label": "Access",
            "value": f"{road['name']} · {status}" if road else status,
            "detail": f"{road['distanceM']} m to nearest road" if road else "no mapped road within 1 km",
            "icon": "access",
        },
        {
            "label": "Power",
            "value": ", ".join(a.name for a in assets if a.kind == "substation") or "no critical asset",
            "detail": f"{sum(1 for a in assets if a.kind == 'substation')} substation(s) within 550 m",
            "icon": "power",
        },
        {
            "label": "People",
            "value": f"{people:,} within 700 m",
            "detail": f"{building.get('name', 'building') if building else 'settlement'} in footprint",
            "icon": "people",
        },
    ]
    if assets:
        site.setdefault("assets", [])
        site["assets"] = [
            {"id": a.id, "name": a.name, "kind": a.kind, "valueEur": a.value_eur, "critical": a.critical}
            for a in assets
        ]
    site["accessStatus"] = status
    site["why"] = why
    if people and not site.get("population"):
        site["population"] = people
    return site


def match_insured_property(lon: float, lat: float, policies: list[dict]) -> dict | None:
    """Geocode-free polygon/point match against a claims property register."""
    point = Point(lon, lat)
    for policy in policies:
        bbox = BBox(*policy["bbox"])
        if bbox.contains(lon, lat):
            return policy
    for policy in policies:
        if metres_between((lon, lat), (policy["lon"], policy["lat"])) < 90:
            return policy
    return None


def context_summary(context: ContextPack) -> dict:
    return {
        "roads": len(context.roads),
        "buildings": len(context.buildings),
        "powerAssets": len(context.power),
        "assets": len(context.assets),
        "populationCells": len(context.population),
        "population": sum(int(c.get("people", 0)) for c in context.population),
    }
