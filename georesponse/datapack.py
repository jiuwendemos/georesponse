"""Build the offline demo packs consumed by the web client.

Run:  python -m georesponse.datapack   (or `georesponse build-demo`)
Writes web/public/data/*.json plus basemaps and evidence images.
"""

from __future__ import annotations

import json
import math
import random

from shapely.geometry import Point, shape
from datetime import datetime, timezone
from pathlib import Path

from . import MODEL_VERSION
from .assessment import one_paragraph, write_assessment
from .config import DATA_DIR, DEFAULT_TEAMS, DEFAULT_WEIGHTS, DEMO_IMAGERY, PILOT, RESPONSE_RADIUS_M
from .context import ContextPack, Asset, context_summary
from .detection import classify_severity
from .geo import BBox, METRES_PER_DEG_LAT, circle_polygon, feature, feature_collection, make_flood_envelopes, metres_between, metres_per_deg_lon
from .mapgen import build_map_layers, make_basemap, make_evidence, make_scene_pair
from .pilot import build_pilot_dashboard, pilot_offer, precision_recall_report
from .ranking import access_factor, coverage_plan, rank_disclosure, rank_sites
from .monitoring import build_monitoring_pack
from .models import model_card
from .packs import all_packs, government_framework, partner_programme
from .security import privacy_review
from .exports import integrations_manifest

WEST_EAST = [
    [7.0550, 50.5330],
    [7.0680, 50.5358],
    [7.0810, 50.5386],
    [7.0940, 50.5402],
    [7.1070, 50.5428],
    [7.1200, 50.5452],
    [7.1330, 50.5468],
    [7.1450, 50.5485],
]

FLOOD_SITES = [
    # id, name, kind, t, side, offset_m, value_eur, population, confidence, extent_m2, access, false_positive
    ("S01", "Ahrweiler Altstadt", "housing", 0.52, -1, 180, 4_800_000, 2100, 0.94, 11800, "blocked", True),
    ("S02", "Bad Neuenahr Kurpark", "care", 0.68, 1, 260, 6_200_000, 1800, 0.91, 9800, "flooded", False),
    ("S03", "Heimersheim Bridge Park", "transport", 0.86, -1, 140, 4_200_000, 900, 0.91, 8600, "blocked", False),
    ("S04", "Heppingen Substation", "substation", 0.60, 1, 420, 8_400_000, 640, 0.90, 6400, "restricted", False),
    ("S05", "Bachem Valley Road", "housing", 0.44, -1, 260, 3_600_000, 1250, 0.86, 5800, "flooded", False),
    ("S06", "Walporzheim Weir", "water", 0.24, -1, 180, 3_500_000, 320, 0.84, 6900, "slow", False),
    ("S07", "Marienthal Monastery", "heritage", 0.34, 1, 500, 5_100_000, 300, 0.88, 4200, "restricted", False),
    ("S08", "Dernau Vineyards", "agriculture", 0.14, 1, 420, 2_800_000, 180, 0.79, 11000, "slow", False),
    ("S09", "Rech Village North", "housing", 0.20, 1, 260, 3_300_000, 980, 0.82, 5300, "blocked", False),
    ("S10", "Mayschoss Winery", "commercial", 0.10, -1, 300, 4_000_000, 260, 0.81, 4700, "clear", False),
    ("S11", "Ahrbrück School", "school", 0.03, 1, 380, 2_600_000, 900, 0.87, 3800, "flooded", False),
    ("S12", "Lohrsdorf Care Farm", "care", 0.30, -1, 620, 1_900_000, 400, 0.76, 3100, "debris", False),
    ("S13", "Gimmigen Greenhouses", "agriculture", 0.56, 1, 720, 1_400_000, 210, 0.71, 2600, "clear", False),
    ("S14", "Landskrone Hill Road", "road", 0.50, 1, 900, 900_000, 150, 0.68, 2100, "restricted", False),
    ("S15", "Ehlingen Pumping Station", "water", 0.92, 1, 380, 5_800_000, 480, 0.85, 3500, "blocked", False),
    ("S16", "Ramersbach Forest Track", "forest", 0.36, 1, 1050, 600_000, 90, 0.63, 1800, "slow", False),
    ("S17", "Kirchdaun Community Hall", "public", 0.40, -1, 500, 1_100_000, 520, 0.74, 2300, "flooded", False),
    ("S18", "Green Campsite", "tourism", 0.96, -1, 260, 800_000, 250, 0.58, 1500, "clear", False),
]

WILDFIRE_NAMES = [
    "Monschau Forest", "Vogelsang Ridge", "Schleiden Edge", "Gemünd South", "Kall Heath",
    "Nideggen Woods", "Heimbach Valley", "Rurberg Shore", "Einruhr Hamlet", "Wolfgarten",
    "Zerkall Mill", "Bergstein Farm", "Hürtgen Treeline", "Roetgen Waterworks",
]
WILDFIRE_KINDS = ["forest", "forest", "housing", "care", "forest", "agriculture", "heritage", "water", "housing", "forest", "commercial", "agriculture", "public", "water"]

CONSTRUCTION_NAMES = [
    "Ehrenfeld Rail Yard", "Müngersdorf Park", "Braunsfeld Depot", "Lindenthal Campus",
    "Sülz Housing Block", "Rodenkirchen Riverside", "Porz Logistics", "Ossendorf Works",
    "Bocklemünd Retail", "Widdersdorf Fields", "Junkersdorf Estate", "Weiden Business Park",
]
CONSTRUCTION_KINDS = ["transport", "public", "commercial", "school", "housing", "housing", "commercial", "commercial", "commercial", "agriculture", "housing", "commercial"]

ACCESS = ["clear", "flooded", "blocked", "restricted", "slow", "debris"]


def _interp(route: list[list[float]], t: float) -> tuple[float, float, float, float]:
    """Return lon, lat, and unit direction of the route at fraction t."""
    lengths = [metres_between(route[i], route[i + 1]) for i in range(len(route) - 1)]
    total = sum(lengths)
    target = max(0.0, min(1.0, t)) * total
    acc = 0.0
    for i, length in enumerate(lengths):
        if acc + length >= target:
            frac = (target - acc) / max(length, 1e-9)
            lon = route[i][0] + (route[i + 1][0] - route[i][0]) * frac
            lat = route[i][1] + (route[i + 1][1] - route[i][1]) * frac
            dx = route[i + 1][0] - route[i][0]
            dy = route[i + 1][1] - route[i][1]
            norm = math.hypot(dx * metres_per_deg_lon(lat), dy * METRES_PER_DEG_LAT) or 1
            return lon, lat, dx * metres_per_deg_lon(lat) / norm, dy * METRES_PER_DEG_LAT / norm
        acc += length
    return route[-1][0], route[-1][1], 1.0, 0.0


def _offset_point(route: list[list[float]], t: float, side: int, offset_m: float) -> tuple[float, float]:
    lon, lat, ux, uy = _interp(route, t)
    # perpendicular (right-hand) vector
    px, py = -uy, ux
    dx = side * px * offset_m
    dy = side * py * offset_m
    return lon + dx / metres_per_deg_lon(lat), lat + dy / METRES_PER_DEG_LAT


def _circle_route(lon: float, lat: float) -> list[list[float]]:
    return [
        [lon - 0.012, lat - 0.003],
        [lon, lat],
        [lon + 0.012, lat + 0.003],
    ]


def _random_sites(prefix: str, names: list[str], kinds: list[str], count: int, center: list[float], seed: int) -> list[dict]:
    rng = random.Random(seed)
    route = _circle_route(center[0], center[1])
    sites = []
    for i in range(count):
        t = 0.06 + 0.88 * i / max(1, count - 1)
        side = 1 if i % 2 == 0 else -1
        offset = rng.choice([160, 220, 300, 380, 520, 700])
        lon, lat = _offset_point(route, t, side, offset)
        extent = rng.randint(1800, 12000)
        confidence = round(rng.uniform(0.62, 0.93), 2)
        sites.append(
            {
                "id": f"{prefix}{i + 1:02d}",
                "name": names[i],
                "kind": kinds[i % len(kinds)],
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "valueEur": rng.choice([600_000, 900_000, 1_400_000, 2_100_000, 2_800_000, 3_600_000, 4_200_000, 5_800_000, 7_100_000]),
                "population": rng.randint(90, 1900),
                "confidence": confidence,
                "changeExtentM2": extent,
                "accessStatus": rng.choice(ACCESS),
                "falsePositive": False,
            }
        )
    return sites


def _make_sites(config: dict) -> list[dict]:
    route = config["route"]
    sites: list[dict] = []
    if config["hazard"] == "flood":
        for sid, name, kind, t, side, offset, value, pop, confidence, extent, access, fp in FLOOD_SITES:
            lon, lat = _offset_point(route, t, side, offset)
            sites.append(
                {
                    "id": sid,
                    "name": name,
                    "kind": kind,
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "valueEur": value,
                    "population": pop,
                    "confidence": confidence,
                    "changeExtentM2": extent,
                    "accessStatus": access,
                    "falsePositive": fp,
                }
            )
    else:
        sites = _random_sites(config["prefix"], config["names"], config["kinds"], config["count"], config["center"], config["seed"])
    return sites


def _radial_frames(center: list[float], hours: list[float], start_m: float, end_m: float, seed: int = 3) -> list[dict]:
    frames = []
    n = len(hours)
    for i, hour in enumerate(hours):
        t = i / max(1, n - 1)
        radius = start_m + (end_m - start_m) * (t ** 1.35)
        geom = circle_polygon(center[0], center[1], radius, steps=48)
        frames.append(
            {
                "t": hour,
                "label": f"{int(hour):02d}:00",
                "areaKm2": round(math.pi * radius * radius / 1_000_000, 1),
                "geometry": {"type": "Polygon", "coordinates": [list(geom.exterior.coords)]},
            }
        )
    return frames


def _severity(extent: int, confidence: float) -> str:
    score = 0.60 * min(1.0, extent / 10000) + 0.40 * confidence
    if score >= 0.72:
        return "red"
    if score >= 0.48:
        return "orange"
    return "yellow"


def _response_minutes(depot: list[float], site: dict) -> int:
    km = metres_between(depot, (site["lon"], site["lat"])) / 1000
    return int(round(4 + km / 38 * 60))


def _kind_label(kind: str) -> str:
    return {
        "housing": "Residential block",
        "care": "Care facility",
        "transport": "Transport asset",
        "substation": "Power substation",
        "water": "Water infrastructure",
        "heritage": "Heritage site",
        "agriculture": "Agricultural asset",
        "commercial": "Commercial asset",
        "school": "School",
        "road": "Road access",
        "forest": "Forest track",
        "public": "Public building",
        "tourism": "Campsite",
    }.get(kind, "Asset")


def _build_context(config: dict, bbox: BBox, sites: list[dict], layers: dict) -> ContextPack:
    assets = []
    for site in sites:
        if site["kind"] in {"substation", "water", "bridge", "transport", "care", "school"}:
            assets.append(
                Asset(
                    id=f"AST-{site['id']}",
                    name=site["name"],
                    kind="substation" if site["kind"] == "substation" else "facility",
                    lon=site["lon"],
                    lat=site["lat"],
                    value_eur=site["valueEur"],
                    critical=site["kind"] in {"substation", "care", "water"},
                )
            )
    roads = [
        {"name": r["name"], "class": r["class"], "coords": [[lon, lat] for lon, lat in r["coords"]]}
        for r in layers["roads"]
    ]
    buildings = layers["buildings"]["features"]
    return ContextPack(
        roads=roads,
        buildings=buildings,
        power=layers["power"]["features"],
        landuse=layers["landuse"]["features"],
        assets=assets,
        population=layers["population"],
    )


def _enrich_sites(sites: list[dict], context: ContextPack, depot: list[float], flood: list[dict]) -> None:
    for site in sites:
        site["severity"] = _severity(site["changeExtentM2"], site["confidence"])
        if flood:
            point = Point(site["lon"], site["lat"])
            hit = next((frame for frame in flood if shape(frame["geometry"]).buffer(0).contains(point)), None)
            site["riskAt"] = hit["t"] if hit else float(flood[-1]["t"]) + 1
            site["flooded"] = bool(hit)
        else:
            site["riskAt"] = 0
            site["flooded"] = False
        site["kindLabel"] = _kind_label(site["kind"])
        site["responseMinutes"] = _response_minutes(depot, site)
        road = context.nearest_road(site["lon"], site["lat"])
        site["why"] = [
            {
                "label": "Access",
                "value": f"{road['name'] if road else 'Unmapped road'} · {site['accessStatus']}",
                "detail": f"{road['distanceM'] if road else '—'} m to the nearest road",
                "icon": "access",
            },
            {
                "label": "Power",
                "value": "Substation in footprint" if site["kind"] == "substation" else ("Critical asset nearby" if site["kind"] in {"care", "water"} else "No critical asset"),
                "detail": f"{site.get('valueEur', 0):,} EUR exposed value",
                "icon": "power",
            },
            {
                "label": "People",
                "value": f"{site.get('population', 0):,} within 700 m",
                "detail": f"{site['kindLabel']} · response {site['responseMinutes']} min",
                "icon": "people",
            },
        ]
        # coverage geometry for team previews
        coverage = circle_polygon(site["lon"], site["lat"], RESPONSE_RADIUS_M, steps=48)
        site["coverage"] = {"type": "Polygon", "coordinates": [list(coverage.exterior.coords)]}
        site["policy"] = {
            "id": f"POL-{config_id(site)}-{site['id']}",
            "holder": f"Policyholder {site['id'][1:]}",
            "propertyType": site["kindLabel"],
            "valueEur": site["valueEur"],
        }
        if site.get("falsePositive"):
            site["falsePositiveReason"] = "Dark roof and wet pavement read as structural damage. The roof edge is intact; the dark shape is water reflection."
        # detection timestamp
        frame = flood[-1] if flood else None
        site["detectedAt"] = f"{frame['label'] if frame else '14:32'} · {MODEL_VERSION}"


def config_id(site: dict) -> str:
    return "PILOT"


def _timeline(config: dict, route: list[list[float]]) -> dict:
    if config["hazard"] == "flood":
        hours = [12 + i * 0.5 for i in range(13)]
        frames = make_flood_envelopes(route, hours=hours, start_width_m=70, end_width_m=900, seed=7)
        return {"mode": "time", "start": 12, "end": 18, "step": 0.5, "caption": "Flood edge over time", "frames": frames}
    if config["hazard"] == "wildfire":
        hours = [12 + i * 0.5 for i in range(13)]
        frames = _radial_frames(config["center"], hours, 180, 2100, seed=5)
        return {"mode": "time", "start": 12, "end": 18, "step": 0.5, "caption": "Burn perimeter over time", "frames": frames}
    frames = []
    labels = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    for i, label in enumerate(labels):
        radius = 260 + i * 210
        geom = circle_polygon(config["center"][0], config["center"][1], radius, steps=40)
        frames.append(
            {
                "t": i,
                "label": label,
                "areaKm2": round(math.pi * radius * radius / 1_000_000, 2),
                "geometry": {"type": "Polygon", "coordinates": [list(geom.exterior.coords)]},
            }
        )
    return {"mode": "period", "start": 0, "end": 6, "step": 1, "caption": "Construction progress", "frames": frames}


SCENARIOS = [
    {
        "id": "ahr-2021-flood",
        "title": "Ahr valley flood",
        "subtitle": "40 km² · 18 priority sites · 3 response teams",
        "hazard": "flood",
        "region": "Ahrweiler, Germany",
        "eventDate": "2021-07-14",
        "eventTime": "14:32",
        "center": [7.100, 50.545],
        "zoom": 12.7,
        "widthKm": 8.0,
        "heightKm": 5.0,
        "teams": 3,
        "accent": "#22d3ee",
        "route": WEST_EAST,
        "seed": 7,
        "basemapWidth": 1500,
        "basemapHeight": 940,
        "audience": ("S04", "S05"),
        "falsePositive": "S01",
        "quote": "We knew where to send the teams before the second coffee.",
    },
    {
        "id": "eifel-2022-wildfire",
        "title": "Eifel ridge wildfire",
        "subtitle": "34 km² · 14 priority sites · 3 response teams",
        "hazard": "wildfire",
        "region": "Eifel, Germany",
        "eventDate": "2022-07-25",
        "eventTime": "13:10",
        "center": [6.420, 50.590],
        "zoom": 12.5,
        "widthKm": 7.4,
        "heightKm": 4.6,
        "teams": 3,
        "accent": "#fbbf24",
        "route": _circle_route(6.420, 50.590),
        "prefix": "W",
        "names": WILDFIRE_NAMES,
        "kinds": WILDFIRE_KINDS,
        "count": 14,
        "seed": 23,
        "basemapWidth": 1200,
        "basemapHeight": 760,
        "audience": ("W04", "W07"),
        "falsePositive": None,
        "quote": "The fire moved. The plan moved with it.",
    },
    {
        "id": "cologne-2024-construction",
        "title": "Cologne construction watch",
        "subtitle": "28 km² · 12 monitored sites · 2 site visits",
        "hazard": "construction",
        "region": "Cologne, Germany",
        "eventDate": "2024-03-12",
        "eventTime": "09:00",
        "center": [6.905, 50.935],
        "zoom": 12.8,
        "widthKm": 6.8,
        "heightKm": 4.2,
        "teams": 2,
        "accent": "#a78bfa",
        "route": _circle_route(6.905, 50.935),
        "prefix": "C",
        "names": CONSTRUCTION_NAMES,
        "kinds": CONSTRUCTION_KINDS,
        "count": 12,
        "seed": 41,
        "basemapWidth": 1100,
        "basemapHeight": 700,
        "audience": ("C03", "C08"),
        "falsePositive": None,
        "quote": "Every new structure on one map, not one hundred tabs.",
    },
]


def build_scenario(config: dict, data_dir: Path = DATA_DIR) -> dict:
    bbox = BBox.around(config["center"][0], config["center"][1], config["widthKm"], config["heightKm"])
    sites = _make_sites(config)
    depot = [config["center"][0] - config["widthKm"] / 2 * 0.6 / (metres_per_deg_lon(config["center"][1]) / 1000), config["center"][1] - 0.006]

    layers = build_map_layers(bbox, config["route"], sites, seed=config["seed"])
    context = _build_context(config, bbox, sites, layers)

    timeline = _timeline(config, config["route"])
    frames = timeline["frames"]
    _enrich_sites(sites, context, depot, frames)

    # ranking
    ranked, warnings = rank_sites(sites)
    for item in ranked:
        item.site["rank"] = item.rank
        item.site["rankScore"] = round(item.score, 4)
        item.site["rankContributions"] = {k: round(v, 4) for k, v in item.contributions.items()}

    # evidence images
    basemap_dir = data_dir / "basemaps"
    basemap_dir.mkdir(parents=True, exist_ok=True)
    basemap_path = basemap_dir / f"{config['id']}.png"
    basemap_info = make_basemap(
        bbox,
        basemap_path,
        width=config["basemapWidth"],
        height=config["basemapHeight"],
        route=config["route"],
        buildings=[],
        roads=[],
        seed=config["seed"],
    )
    evidence_dir = data_dir / "evidence" / config["id"]
    for site in sites:
        site["evidence"] = make_evidence(
            basemap_path,
            bbox,
            site,
            evidence_dir,
            change_type=config["hazard"],
            seed=config["seed"],
        )
    scene_pair = make_scene_pair(
        basemap_path,
        bbox,
        frames[-1]["geometry"] if frames else None,
        data_dir / "scenes",
        hazard=config["hazard"],
        name=config["id"],
    )

    # assessment before and after the trust beat
    assessment = write_assessment({"meta": _meta(config, bbox, sites, timeline, basemap_info), "sites": sites}, ranked, teams=config["teams"])
    false_id = config.get("falsePositive")
    reviews_after = {false_id: "rejected"} if false_id else {}
    ranked_after, _ = rank_sites(sites, exclude={false_id} if false_id else set())
    assessment_after = write_assessment(
        {"meta": _meta(config, bbox, sites, timeline, basemap_info), "sites": sites},
        ranked_after,
        reviews=reviews_after,
        teams=config["teams"],
    )

    audience_a, audience_b = config["audience"]
    site_a = next((s for s in sites if s["id"] == audience_a), None)
    site_b = next((s for s in sites if s["id"] == audience_b), None)

    scenario = {
        "meta": _meta(config, bbox, sites, timeline, basemap_info),
        "sites": sites,
        "timeline": timeline,
        "imageryPair": scene_pair,
        "map": {
            "basemap": {**basemap_info, "file": f"data/basemaps/{config['id']}.png"},
            "roads": feature_collection(layers["roads"] and [feature({"type": "LineString", "coordinates": r["coords"]}, {"name": r["name"], "class": r["class"]}) for r in layers["roads"]]),
            "buildings": layers["buildings"],
            "landuse": layers["landuse"],
            "power": layers["power"],
            "water": layers["water"],
            "boundaries": layers["boundaries"],
            "population": layers["population"],
        },
        "context": context_summary(context),
        "ranking": rank_disclosure(ranked),
        "rankingAfterReview": rank_disclosure(ranked_after),
        "coveragePlan": coverage_plan(ranked_after, config["teams"]),
        "warnings": warnings,
        "falsePositive": {
            "siteId": false_id,
            "title": "Dark roof + wet pavement read as structural damage",
            "agentConfidence": next((s["confidence"] for s in sites if s["id"] == false_id), None),
            "analystReason": "Roof edge is intact; the dark shape is water reflection.",
            "correction": "Water reflection — not a collapsed roof. Finding rejected.",
            "lesson": "The model was confident. The analyst was right. This is why a human signs the assessment.",
            "narrative": "The top-ranked site is a false positive: a dark roof and wet pavement read as structural damage. The analyst rejects it with a visible reason, the ranking re-orders, and a team is freed.",
        }
        if false_id
        else None,
        "audience": {
            "prompt": "Team 3 is free. Where does it go?",
            "a": _audience_candidate(site_a, depot),
            "b": _audience_candidate(site_b, depot),
            "tradeoff": "A substation on open road keeps power on. Dense housing keeps people safe. Both are defensible; the room decides.",
        },
        "assessment": assessment,
        "assessmentAfterReview": assessment_after,
        "fieldOrder": _field_order(config, sites, ranked_after, assessment_after, reviews_after),
        "reviewPolicy": {
            "batchThreshold": 0.90,
            "slaHours": PILOT.review_sla_hours,
            "actions": ["approve", "flag", "reject"],
            "humanInTheLoop": True,
        },
        "provenance": {
            "imagery": DEMO_IMAGERY,
            "model": MODEL_VERSION,
            "weights": DEFAULT_WEIGHTS,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "disclaimer": "Simulated demo data pack. Not for operational decisions. Human review is mandatory. Production uses licensed imagery and adjuster-confirmed labels.",
            "dataRights": [
                "Sentinel data: free and open, attribution required.",
                "OpenStreetMap: ODbL, display © OpenStreetMap contributors.",
                "Copernicus EMS maps have their own terms — verify before use.",
                "Commercial imagery (Planet, Maxar, Airbus) needs a licence even for a demo.",
            ],
        },
        "hero": {
            "areaKm2": 40,
            "sites": len(sites),
            "teams": config["teams"],
            "minutes": PILOT.assessment_minutes,
            "baselineMinutes": PILOT.baseline_minutes,
            "quote": config["quote"],
            "depot": [round(depot[0], 6), round(depot[1], 6)],
        },
    }
    return scenario


def _meta(config: dict, bbox: BBox, sites: list[dict], timeline: dict, basemap: dict) -> dict:
    return {
        "id": config["id"],
        "title": config["title"],
        "subtitle": config["subtitle"],
        "hazard": config["hazard"],
        "region": config["region"],
        "eventDate": config["eventDate"],
        "eventTime": config["eventTime"],
        "center": config["center"],
        "zoom": config["zoom"],
        "bbox": bbox.as_list(),
        "areaKm2": round(bbox.area_km2, 1),
        "teams": config["teams"],
        "accent": config["accent"],
        "baselineMinutes": PILOT.baseline_minutes,
        "assessmentMinutes": PILOT.assessment_minutes,
        "imagery": {
            "source": DEMO_IMAGERY["source"],
            "attribution": DEMO_IMAGERY["attribution"],
            "resolution": DEMO_IMAGERY["resolution"],
            "simulated": True,
            "acquired": f"{config['eventDate']}T10:30:00Z",
        },
        "model": MODEL_VERSION,
        "weights": DEFAULT_WEIGHTS,
        "disclaimer": "Simulated demo pack for the stage and booth. Human review is mandatory.",
        "teams": config["teams"],
        "sites": len(sites),
        "timeline": {"mode": timeline["mode"], "start": timeline["start"], "end": timeline["end"], "step": timeline["step"]},
        "basemap": basemap,
    }


def _audience_candidate(site: dict | None, depot: list[float]) -> dict | None:
    if not site:
        return None
    return {
        "id": site["id"],
        "name": site["name"],
        "severity": site["severity"],
        "confidence": site["confidence"],
        "valueEur": site["valueEur"],
        "population": site["population"],
        "access": site["accessStatus"],
        "responseMinutes": site["responseMinutes"],
        "coverage": site["coverage"],
        "kindLabel": site["kindLabel"],
        "why": site["why"],
        "consequence": _consequence(site),
    }


def _consequence(site: dict) -> str:
    if site["kind"] == "substation":
        return f"Power stays on for {site['valueEur']:,} EUR of asset value; the dense housing block stays uncovered."
    if site["kind"] in {"care", "school"}:
        return f"{site['population']:,} vulnerable people get a team; the power asset stays on the watch list."
    return f"{site['population']:,} people and {site['valueEur']:,} EUR of value get a team; the power asset stays on the watch list."


def _field_order(config: dict, sites: list[dict], ranked, assessment: dict, reviews: dict) -> dict:
    assignments = {}
    for i, item in enumerate(ranked[: config["teams"]]):
        assignments[item.site["id"]] = f"Team {i + 1}"
    by_id = {s["id"]: s for s in sites}
    return {
        "issuedAt": f"{config['eventDate']} {config['eventTime']}",
        "incident": config["title"],
        "region": config["region"],
        "summary": assessment["summary"],
        "assignments": [
            {
                "team": team,
                "siteId": sid,
                "siteName": by_id[sid]["name"],
                "severity": by_id[sid]["severity"],
                "access": by_id[sid]["accessStatus"],
                "responseMinutes": by_id[sid]["responseMinutes"],
            }
            for sid, team in assignments.items()
        ],
        "unassigned": [s["id"] for s in sites if s["id"] not in assignments],
        "assessmentMinutes": PILOT.assessment_minutes,
        "baselineMinutes": PILOT.baseline_minutes,
        "signature": "Analyst: A. Weber · Human review required",
        "modelVersion": MODEL_VERSION,
        "imagery": DEMO_IMAGERY["source"],
        "quote": config["quote"],
    }


def _regional_events() -> dict:
    events = [
        {"id": "EV-01", "name": "Ahr valley flood", "lon": 7.100, "lat": 50.545, "severity": "red", "sites": 18, "approved": 16, "date": "2026-05-06"},
        {"id": "EV-02", "name": "Rur valley flood", "lon": 6.420, "lat": 50.760, "severity": "orange", "sites": 16, "approved": 14, "date": "2026-05-28"},
        {"id": "EV-03", "name": "Eifel ridge wildfire", "lon": 6.420, "lat": 50.590, "severity": "red", "sites": 14, "approved": 12, "date": "2026-06-11"},
        {"id": "EV-04", "name": "Cologne construction watch", "lon": 6.905, "lat": 50.935, "severity": "yellow", "sites": 12, "approved": 9, "date": "2026-06-24"},
        {"id": "EV-05", "name": "Kall storm damage", "lon": 6.560, "lat": 50.540, "severity": "orange", "sites": 9, "approved": 8, "date": "2026-07-02"},
        {"id": "EV-06", "name": "Ahrweiler roof survey", "lon": 7.080, "lat": 50.535, "severity": "yellow", "sites": 22, "approved": 19, "date": "2026-07-18"},
    ]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "center": [6.85, 50.72],
        "bbox": [6.20, 50.30, 7.50, 51.10],
        "events": events,
        "summary": {"events": len(events), "sites": sum(e["sites"] for e in events), "approved": sum(e["approved"] for e in events)},
    }


def _monitoring_pack() -> dict:
    regions = [
        {"id": "AHR", "name": "Ahr corridor", "observedChange": 0.31, "history": [0.04, 0.05, 0.03, 0.06, 0.04, 0.05, 0.04]},
        {"id": "RUR", "name": "Rur valley", "observedChange": 0.12, "history": [0.05, 0.06, 0.04, 0.05, 0.07, 0.06]},
        {"id": "EIF", "name": "Eifel north", "observedChange": 0.09, "history": [0.06, 0.04, 0.05, 0.07, 0.06, 0.05]},
        {"id": "KOL", "name": "Cologne west", "observedChange": 0.18, "history": [0.02, 0.03, 0.02, 0.04, 0.03, 0.02]},
        {"id": "KAL", "name": "Kall corridor", "observedChange": 0.26, "history": [0.03, 0.03, 0.04, 0.02, 0.03, 0.02]},
        {"id": "BON", "name": "Bonn south", "observedChange": 0.05, "history": [0.04, 0.04, 0.05, 0.05, 0.04, 0.04]},
    ]
    pack = build_monitoring_pack(regions)
    return pack


def build_all(data_dir: str | Path = DATA_DIR) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    index_entries = []
    for config in SCENARIOS:
        scenario = build_scenario(config, data_dir)
        path = data_dir / "scenarios" / f"{config['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(scenario, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index_entries.append(
            {
                "id": config["id"],
                "title": config["title"],
                "subtitle": config["subtitle"],
                "hazard": config["hazard"],
                "region": config["region"],
                "date": config["eventDate"],
                "center": config["center"],
                "zoom": config["zoom"],
                "teams": config["teams"],
                "sites": len(scenario["sites"]),
                "accent": config["accent"],
                "thumb": f"data/basemaps/{config['id']}.png",
                "quote": config["quote"],
            }
        )
    index = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "default": SCENARIOS[0]["id"],
        "scenarios": index_entries,
        "model": MODEL_VERSION,
    }
    (data_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (data_dir / "pilot.json").write_text(json.dumps(build_pilot_dashboard(), indent=2), encoding="utf-8")
    (data_dir / "precision-recall.json").write_text(json.dumps(precision_recall_report(), indent=2), encoding="utf-8")
    (data_dir / "monitoring.json").write_text(json.dumps(_monitoring_pack(), indent=2), encoding="utf-8")
    (data_dir / "regional-events.json").write_text(json.dumps(_regional_events(), indent=2), encoding="utf-8")
    (data_dir / "pilot-offer.json").write_text(json.dumps(pilot_offer(), indent=2), encoding="utf-8")
    (data_dir / "privacy.json").write_text(json.dumps(privacy_review({"lawful_basis", "minimisation", "access", "human_review"}), indent=2), encoding="utf-8")
    (data_dir / "integrations.json").write_text(json.dumps(integrations_manifest(), indent=2), encoding="utf-8")
    (data_dir / "model-card.json").write_text(json.dumps(model_card(), indent=2), encoding="utf-8")
    (data_dir / "packs.json").write_text(
        json.dumps({"packs": all_packs(), "partner": partner_programme(), "government": government_framework()}, indent=2),
        encoding="utf-8",
    )
    (data_dir / "npu.json").write_text(
        json.dumps(
            {
                "device": "Ascend 310P (demo configuration)",
                "batchSize": 8,
                "tilesPerMinute": 2140,
                "models": [{"name": "gr-changenet", "version": MODEL_VERSION, "pinned": True}],
                "note": "Optional on-site inference. The demo runs without an NPU; this is the deployment profile.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"scenarios": len(index_entries), "dataDir": str(data_dir), "bytes": sum(p.stat().st_size for p in data_dir.rglob("*") if p.is_file())}


if __name__ == "__main__":
    print(json.dumps(build_all(), indent=2))
