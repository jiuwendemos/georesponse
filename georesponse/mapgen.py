"""Deterministic map and evidence generation for the offline demo pack.

This is the part that makes the stage piece look like a real place without a
network: a procedural orthophoto crop, OSM-shaped layers, and per-site evidence
images.  Every output is labelled as simulated in the app's provenance panel.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .geo import BBox, feature, feature_collection, metres_per_deg_lon

WATER = "#0d3c4a"
FOREST = "#14352b"
FIELD = "#243a2c"
MEADOW = "#2d4432"
URBAN = "#243036"


def _project(bbox: BBox, lon: float, lat: float, width: int, height: int) -> tuple[float, float]:
    x = (lon - bbox.west) / (bbox.east - bbox.west) * width
    y = (bbox.north - lat) / (bbox.north - bbox.south) * height
    return x, y


def _noise_layer(width: int, height: int, seed: int, scale: int = 6) -> np.ndarray:
    rng = np.random.default_rng(seed)
    small = rng.normal(0, 1, (max(2, height // scale), max(2, width // scale)))
    spread = float(small.max() - small.min()) or 1.0
    image = Image.fromarray(((small - small.min()) / spread * 255).astype(np.uint8))
    resized = image.resize((width, height), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    return np.asarray(resized, dtype=np.float32) / 255.0


def _poly(draw: ImageDraw.ImageDraw, bbox: BBox, coords, width: int, height: int, fill, outline=None):  # type: ignore[no-untyped-def]
    points = [_project(bbox, lon, lat, width, height) for lon, lat in coords]
    draw.polygon(points, fill=fill, outline=outline)


def make_basemap(
    bbox: BBox,
    path: str | Path,
    *,
    width: int = 1400,
    height: int = 900,
    route: list[list[float]] | None = None,
    buildings: list[dict] | None = None,
    roads: list[dict] | None = None,
    seed: int = 11,
) -> dict:
    """Paint a satellite-looking raster: fields, forest, urban, river, roads."""
    rng = random.Random(seed)
    noise = _noise_layer(width, height, seed)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[:, :] = np.array([9, 22, 20], dtype=np.float32) / 255.0
    base += (noise[..., None] - 0.5) * 0.06
    image = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(image, "RGBA")

    # Fields: irregular rotated rectangles in muted olive / straw.
    for i in range(46):
        cx = rng.uniform(0, width)
        cy = rng.uniform(0, height)
        w = rng.uniform(width * 0.025, width * 0.09)
        h = rng.uniform(height * 0.025, height * 0.085)
        angle = rng.uniform(-0.5, 0.5)
        color = rng.choice(
            [
                (46, 62, 43, 150),
                (56, 64, 40, 140),
                (38, 56, 42, 150),
                (64, 58, 38, 120),
                (30, 47, 36, 160),
            ]
        )
        box = Image.new("RGBA", (int(w * 2), int(h * 2)), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        bd.rectangle([w * 0.5, h * 0.5, w * 1.5, h * 1.5], fill=color)
        box = box.rotate(math.degrees(angle), resample=Image.Resampling.BICUBIC, expand=False)
        image.paste(box, (int(cx - w), int(cy - h)), box)

    # Forest patches
    for i in range(26):
        cx = rng.uniform(0, width)
        cy = rng.uniform(0, height)
        rx = rng.uniform(width * 0.04, width * 0.13)
        ry = rng.uniform(height * 0.04, height * 0.12)
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(17, 45, 34, 135))

    # Urban patches around the route
    if route:
        for i in range(0, len(route) - 1):
            for side in (-1, 1):
                jitter = rng.uniform(0.002, 0.006)
                lon, lat = route[i]
                lon += side * jitter * rng.uniform(0.3, 1.0)
                lat += side * jitter * 0.4
                x, y = _project(bbox, lon, lat, width, height)
                rx = rng.uniform(width * 0.012, width * 0.035)
                ry = rng.uniform(height * 0.012, height * 0.03)
                draw.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(41, 48, 52, 120))

    # River ribbon
    if route:
        points = [_project(bbox, lon, lat, width, height) for lon, lat in route]
        for width_px, color in ((max(7, int(width / 120)), (15, 62, 76, 255)), (max(3, int(width / 260)), (22, 92, 108, 220))):
            draw.line(points, fill=color, width=width_px, joint="curve")
        # floodplain fringe
        fringe = [(x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)) for x, y in points]
        draw.line(fringe, fill=(24, 74, 72, 90), width=max(18, int(width / 45)), joint="curve")

    # Roads
    if roads:
        for road in roads:
            pts = [_project(bbox, lon, lat, width, height) for lon, lat in road.get("coords", [])]
            if len(pts) < 2:
                continue
            cls = road.get("class", "local")
            w = {"primary": 5, "secondary": 3, "local": 1.4}.get(cls, 1)
            draw.line(pts, fill=(96, 104, 104, 190 if cls == "local" else 235), width=max(1, int(w)), joint="curve")

    # Buildings
    if buildings:
        for building in buildings:
            ring = building["geometry"]["coordinates"][0]
            pts = [_project(bbox, lon, lat, width, height) for lon, lat in ring]
            shade = rng.choice([(92, 98, 100, 230), (110, 104, 92, 220), (74, 82, 86, 230)])
            draw.polygon(pts, fill=shade)
            # roof highlight on one edge
            if len(pts) >= 4:
                draw.line([pts[0], pts[1]], fill=(150, 145, 130, 160), width=1)

    # Grain + bloom
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr += (noise[..., None] - 0.5) * 0.045
    yy, xx = np.mgrid[0:height, 0:width]
    vignette = 1 - 0.28 * (((xx - width / 2) ** 2 / (width / 2) ** 2) + ((yy - height / 2) ** 2 / (height / 2) ** 2))
    arr *= np.clip(vignette, 0.5, 1.0)[..., None]
    image = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(0.5))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return {"file": path.name, "width": width, "height": height, "bounds": bbox.as_list()}


def build_map_layers(
    bbox: BBox,
    route: list[list[float]],
    sites: list[dict],
    *,
    seed: int = 11,
) -> dict:
    rng = random.Random(seed)
    roads: list[dict] = []
    buildings: list[dict] = []
    landuse: list[dict] = []
    power: list[dict] = []
    population: list[dict] = []

    # Main road follows the river with a slight north offset
    main = [[lon, lat + 0.00265] for lon, lat in route]
    roads.append({"name": "B267", "class": "primary", "coords": main})
    river_road = [[lon, lat - 0.00185] for lon, lat in route]
    roads.append({"name": "Ahrstraße", "class": "secondary", "coords": river_road})

    for index, site in enumerate(sites):
        lon, lat = site["lon"], site["lat"]
        # connector road from site to the main road
        anchor = min(main, key=lambda p: (p[0] - lon) ** 2 + (p[1] - lat) ** 2)
        roads.append(
            {
                "name": f"{site['name']} access",
                "class": "local",
                "coords": [[lon, lat], [lon * 0.5 + anchor[0] * 0.5, lat * 0.5 + anchor[1] * 0.5], anchor],
            }
        )
        # local street grid
        for k in range(3):
            dy = (k - 1) * 0.00075
            roads.append(
                {
                    "name": f"Local street {index + 1}-{k + 1}",
                    "class": "local",
                    "coords": [[lon - 0.0022, lat + dy], [lon + 0.0022, lat + dy + 0.0002]],
                }
            )
        # building cluster
        for b in range(rng.randint(22, 46)):
            dx = rng.uniform(-0.0034, 0.0034)
            dy = rng.uniform(-0.0024, 0.0024)
            w = rng.uniform(0.00010, 0.00034)
            h = rng.uniform(0.00008, 0.00026)
            cx, cy = lon + dx, lat + dy
            ring = [
                [cx - w, cy - h],
                [cx + w, cy - h],
                [cx + w, cy + h],
                [cx - w, cy + h],
                [cx - w, cy - h],
            ]
            buildings.append(
                feature(
                    {"type": "Polygon", "coordinates": [ring]},
                    {"id": f"b{index}-{b}", "kind": "building", "name": f"Building {index + 1}.{b + 1}"},
                )
            )
        # land use plot
        landuse.append(
            feature(
                {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - 0.0045, lat - 0.0032],
                        [lon + 0.0048, lat - 0.0036],
                        [lon + 0.0044, lat + 0.0034],
                        [lon - 0.0042, lat + 0.0038],
                        [lon - 0.0045, lat - 0.0032],
                    ]],
                },
                {
                    "kind": rng.choice(["residential", "vineyard", "meadow", "commercial"]),
                    "name": f"{site['name']} land use",
                },
            )
        )
        population.append(
            {
                "lon": round(lon, 5),
                "lat": round(lat, 5),
                "people": int(site.get("population", 200)),
            }
        )

    # Forest / vineyard blocks
    for i in range(18):
        west = bbox.west + (bbox.east - bbox.west) * (i / 18) + rng.uniform(0, 0.004)
        south = bbox.south + rng.uniform(0.002, 0.012)
        width = rng.uniform(0.004, 0.011)
        height = rng.uniform(0.003, 0.008)
        landuse.append(
            feature(
                {
                    "type": "Polygon",
                    "coordinates": [[
                        [west, south],
                        [west + width, south + 0.0004],
                        [west + width - 0.0003, south + height],
                        [west + 0.0002, south + height - 0.0003],
                        [west, south],
                    ]],
                },
                {"kind": rng.choice(["forest", "vineyard", "meadow"]), "name": f"Plot {i + 1}"},
            )
        )

    # Power lines + substations
    power_sites = [s for s in sites if s.get("kind") in {"substation", "water", "bridge"}]
    coords = [[s["lon"], s["lat"]] for s in power_sites]
    for i in range(len(coords) - 1):
        power.append(
            feature(
                {"type": "LineString", "coordinates": [coords[i], coords[i + 1]]},
                {"kind": "line", "name": f"MV feeder {i + 1}", "voltage": "20 kV"},
            )
        )
    for site in power_sites:
        power.append(
            feature(
                {"type": "Point", "coordinates": [site["lon"], site["lat"]]},
                {"kind": "substation", "name": site["name"], "critical": site["id"] in {"S04", "S15"}},
            )
        )

    water = [
        feature(
            {"type": "LineString", "coordinates": route},
            {"kind": "river", "name": "Ahr", "width": "river"},
        )
    ]
    for site in sites:
        if site.get("kind") == "water":
            water.append(
                feature(
                    {"type": "Point", "coordinates": [site["lon"], site["lat"]]},
                    {"kind": "weir", "name": site["name"]},
                )
            )

    boundary = feature(
        bbox.to_polygon(),
        {"kind": "district", "name": "Ahrweiler district", "areaKm2": round(bbox.area_km2, 1)},
    )

    return {
        "roads": roads,
        "buildings": feature_collection(buildings),
        "landuse": feature_collection(landuse),
        "power": feature_collection(power),
        "water": feature_collection(water),
        "population": population,
        "boundaries": feature_collection([boundary]),
    }


def make_evidence(
    basemap: str | Path,
    bbox: BBox,
    site: dict,
    out_dir: str | Path,
    *,
    change_type: str,
    seed: int = 11,
) -> dict:
    """Crop the orthophoto around the site and paint a before/after pair."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Image.open(basemap).convert("RGB")
    full_w, full_h = base.size
    cx = (site["lon"] - bbox.west) / (bbox.east - bbox.west) * full_w
    cy = (bbox.north - site["lat"]) / (bbox.north - bbox.south) * full_h
    half_w = full_w * 0.075
    half_h = full_h * 0.095
    box = (int(max(0, cx - half_w)), int(max(0, cy - half_h)), int(min(full_w, cx + half_w)), int(min(full_h, cy + half_h)))
    crop = base.crop(box).resize((420, 280), Image.Resampling.LANCZOS)
    before = crop.copy()
    after = crop.copy()
    draw = ImageDraw.Draw(after, "RGBA")
    rng = random.Random(seed + int(site["id"][1:]))

    if change_type == "flood":
        # water rising over the lower part of the frame
        water_h = 80 + int(site.get("confidence", 0.8) * 70)
        draw.rectangle([0, 280 - water_h, 420, 280], fill=(30, 105, 122, 150))
        draw.line([(0, 280 - water_h + 12), (140, 280 - water_h), (280, 280 - water_h + 8), (420, 280 - water_h - 4)], fill=(120, 220, 235, 120), width=2)
    elif change_type == "burn":
        draw.rectangle([0, 0, 420, 280], fill=(40, 24, 16, 95))
        for i in range(90):
            x, y = rng.randint(0, 420), rng.randint(0, 280)
            r = rng.randint(1, 4)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(20, 14, 10, 160))
    else:
        draw.rectangle([70, 60, 350, 230], fill=(120, 100, 70, 70))
        for i in range(18):
            x = 90 + i * 14
            draw.rectangle([x, 80, x + 10, 210], fill=(170, 130, 70, 60))

    # detection box
    box_x = 120 + rng.randint(0, 30)
    box_y = 92 + rng.randint(0, 20)
    draw.rectangle([box_x, box_y, box_x + 170, box_y + 108], outline=(251, 113, 133, 230), width=2)
    draw.text((box_x + 4, box_y - 12), f"{site['id']} · {site.get('severity', 'red')} · {int(site.get('confidence', 0.8) * 100)}%", fill=(255, 220, 220, 255))

    if site.get("falsePositive"):
        # The trust beat: a dark roof and a water reflection, no structural damage.
        draw.rectangle([150, 120, 250, 190], fill=(24, 26, 28, 255))
        draw.line([(150, 120), (250, 120)], fill=(190, 190, 180, 220), width=2)
        draw.ellipse([250, 170, 340, 225], fill=(70, 150, 175, 90))

    before_name = f"{site['id'].lower()}-before.png"
    after_name = f"{site['id'].lower()}-after.png"
    before.save(out_dir / before_name, optimize=True)
    after.save(out_dir / after_name, optimize=True)
    return {
        "before": f"data/evidence/{out_dir.name}/{before_name}",
        "after": f"data/evidence/{out_dir.name}/{after_name}",
        "caption": f"{site['id']} · {'simulated' if True else ''} Sentinel-2-like crop · 10 m",
    }


def make_scene_pair(
    basemap: str | Path,
    bbox: BBox,
    geometry: dict | None,
    out_dir: str | Path,
    *,
    hazard: str,
    name: str,
) -> dict:
    """Whole-scene before/after pair for the provenance panel and the booth."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Image.open(basemap).convert("RGB").resize((1400, 875), Image.Resampling.LANCZOS)
    before = base.copy()
    after = base.copy()
    if geometry:
        overlay = Image.new("RGBA", after.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")
        colors = {
            "flood": (34, 211, 238, 95),
            "wildfire": (249, 115, 22, 95),
            "construction": (167, 139, 250, 80),
        }
        fill = colors.get(hazard, colors["flood"])
        polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for poly in polys:
            for ring in poly:
                pts = []
                for lon, lat in ring:
                    x = (lon - bbox.west) / (bbox.east - bbox.west) * after.width
                    y = (bbox.north - lat) / (bbox.north - bbox.south) * after.height
                    pts.append((x, y))
                if len(pts) > 2:
                    draw.polygon(pts, fill=fill)
        after = Image.alpha_composite(after.convert("RGBA"), overlay).convert("RGB")
    before_path = out_dir / f"{name}-before.png"
    after_path = out_dir / f"{name}-after.png"
    before.save(before_path, optimize=True)
    after.save(after_path, optimize=True)
    return {
        "before": f"data/scenes/{before_path.name}",
        "after": f"data/scenes/{after_path.name}",
        "caption": f"{name} · before / after · simulated Sentinel-2-like composite",
    }


def make_real_evidence(
    before_path: str | Path,
    after_path: str | Path,
    bbox: BBox,
    site: dict,
    out_dir: str | Path,
    *,
    seed: int = 11,
) -> dict:
    """Crop a real Sentinel-2 before/after pair around a site."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    before_img = Image.open(before_path).convert("RGB")
    after_img = Image.open(after_path).convert("RGB")
    full_w, full_h = after_img.size
    cx = (site["lon"] - bbox.west) / (bbox.east - bbox.west) * full_w
    cy = (bbox.north - site["lat"]) / (bbox.north - bbox.south) * full_h
    half_w = full_w * 0.032
    half_h = full_h * 0.045
    box = (int(max(0, cx - half_w)), int(max(0, cy - half_h)), int(min(full_w, cx + half_w)), int(min(full_h, cy + half_h)))
    before = before_img.crop(box).resize((420, 280), Image.Resampling.LANCZOS)
    after = after_img.crop(box).resize((420, 280), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(after, "RGBA")
    rng = random.Random(seed + int(site["id"][1:]))
    x = 110 + rng.randint(0, 40)
    y = 84 + rng.randint(0, 24)
    draw.rectangle([x, y, x + 190, y + 118], outline=(251, 113, 133, 240), width=2)
    draw.text((x + 4, y - 12), f"{site['id']} · {site.get('severity', 'red')} · {int(site.get('confidence', 0.8) * 100)}%", fill=(255, 230, 230, 255))
    before_name = f"{site['id'].lower()}-before.png"
    after_name = f"{site['id'].lower()}-after.png"
    before.save(out_dir / before_name, optimize=True)
    after.save(out_dir / after_name, optimize=True)
    return {
        "before": f"data/evidence/{out_dir.name}/{before_name}",
        "after": f"data/evidence/{out_dir.name}/{after_name}",
        "caption": f"{site['id']} · Sentinel-2 L2A before/after · 10 m · change overlay",
    }
