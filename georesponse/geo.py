"""Geometry helpers: local projection, tiles, flood envelopes and map layers.

Shapely is used for real geometry work; pyproj is used when it is available so
the same code can normalise EPSG:4326, EPSG:3857 and UTM inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

try:  # pragma: no cover - optional precision path
    from pyproj import Transformer

    HAVE_PYPROJ = True
except Exception:  # pragma: no cover
    Transformer = None  # type: ignore
    HAVE_PYPROJ = False


EARTH_RADIUS_M = 6_371_008.8
METRES_PER_DEG_LAT = 111_320.0


def metres_per_deg_lon(lat: float) -> float:
    return METRES_PER_DEG_LAT * math.cos(math.radians(lat))


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    @property
    def width_m(self) -> float:
        return (self.east - self.west) * metres_per_deg_lon((self.south + self.north) / 2)

    @property
    def height_m(self) -> float:
        return (self.north - self.south) * METRES_PER_DEG_LAT

    @property
    def area_km2(self) -> float:
        return self.width_m * self.height_m / 1_000_000

    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]

    def to_polygon(self) -> Polygon:
        return box(self.west, self.south, self.east, self.north)

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    @classmethod
    def around(cls, lon: float, lat: float, width_km: float, height_km: float) -> "BBox":
        dx = width_km * 1000 / 2 / metres_per_deg_lon(lat)
        dy = height_km * 1000 / 2 / METRES_PER_DEG_LAT
        return cls(lon - dx, lat - dy, lon + dx, lat + dy)


def circle_polygon(lon: float, lat: float, radius_m: float, steps: int = 72) -> Polygon:
    """Geodesic-ish circle in EPSG:4326 (good enough at city scale)."""
    lat_rad = math.radians(lat)
    coords: list[tuple[float, float]] = []
    for i in range(steps):
        bearing = 2 * math.pi * i / steps
        dlat = (radius_m * math.cos(bearing)) / EARTH_RADIUS_M
        dlon = (radius_m * math.sin(bearing)) / (EARTH_RADIUS_M * math.cos(lat_rad))
        coords.append((lon + math.degrees(dlon), lat + math.degrees(dlat)))
    return Polygon(coords)


def metres_between(a: Sequence[float], b: Sequence[float]) -> float:
    """Haversine distance between two [lon, lat] points."""
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def to_metric(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """Cheap local equirectangular projection in metres."""
    return (
        (lon - lon0) * metres_per_deg_lon(lat0),
        (lat - lat0) * METRES_PER_DEG_LAT,
    )


def from_metric(x: float, y: float, lon0: float, lat0: float) -> tuple[float, float]:
    return (lon0 + x / metres_per_deg_lon(lat0), lat0 + y / METRES_PER_DEG_LAT)


def normalise_crs(geometry: BaseGeometry, src_crs: str, dst_crs: str = "EPSG:4326") -> BaseGeometry:
    """Project a geometry to WGS84.  Falls back to identity without pyproj."""
    if src_crs.upper() == dst_crs.upper() or not HAVE_PYPROJ:
        return geometry
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)  # type: ignore[union-attr]
    return _transform_geometry(geometry, transformer.transform)


def _transform_geometry(geometry: BaseGeometry, fn) -> BaseGeometry:  # type: ignore[no-untyped-def]
    if geometry.geom_type == "Polygon":
        return Polygon([fn(x, y) for x, y in geometry.exterior.coords], [
            [fn(x, y) for x, y in ring.coords] for ring in geometry.interiors
        ])
    if geometry.geom_type == "MultiPolygon":
        return MultiPolygon([_transform_geometry(p, fn) for p in geometry.geoms])
    if geometry.geom_type == "LineString":
        return type(geometry)([fn(x, y) for x, y in geometry.coords])
    if geometry.geom_type == "Point":
        return Point(fn(geometry.x, geometry.y))
    return geometry


def tile_grid(bbox: BBox, tile_size_m: float = 512.0) -> list[dict]:
    """Split a bbox into a metric tile grid with WGS84 bounds."""
    lat0 = (bbox.south + bbox.north) / 2
    lon0 = (bbox.west + bbox.east) / 2
    width = bbox.width_m
    height = bbox.height_m
    cols = max(1, math.ceil(width / tile_size_m))
    rows = max(1, math.ceil(height / tile_size_m))
    tiles: list[dict] = []
    for row in range(rows):
        for col in range(cols):
            x0 = -width / 2 + col * tile_size_m
            y1 = height / 2 - row * tile_size_m
            x1 = min(x0 + tile_size_m, width / 2)
            y0 = max(y1 - tile_size_m, -height / 2)
            west, south = from_metric(x0, y0, lon0, lat0)
            east, north = from_metric(x1, y1, lon0, lat0)
            tiles.append(
                {
                    "id": f"r{row:02d}c{col:02d}",
                    "row": row,
                    "col": col,
                    "bounds": [west, south, east, north],
                    "size_m": tile_size_m,
                }
            )
    return tiles


def make_flood_envelopes(
    river: Sequence[Sequence[float]],
    *,
    hours: Sequence[float],
    start_width_m: float,
    end_width_m: float,
    valley: Polygon | None = None,
    seed: int = 7,
) -> list[dict]:
    """Grow a flood envelope along a river centreline.

    The width grows non-linearly (a flood accelerates then plateaus), and a
    deterministic wobble creates the irregular edge a real inundation map has.
    """
    if len(river) < 2:
        raise ValueError("river needs at least two points")
    lat0 = sum(p[1] for p in river) / len(river)
    lon0 = sum(p[0] for p in river) / len(river)
    line = [to_metric(lon, lat, lon0, lat0) for lon, lat in river]
    from shapely.geometry import LineString

    river_line = LineString(line)
    frames: list[dict] = []
    n = len(hours)
    for i, hour in enumerate(hours):
        t = i / max(1, n - 1)
        # logistic growth: slow start, fast middle, plateaus
        growth = 1 / (1 + math.exp(-8 * (t - 0.45)))
        width = start_width_m + (end_width_m - start_width_m) * growth
        # A continuous inundation ribbon, with a deterministic edge wobble.
        buffered = river_line.buffer(width, quad_segs=10)
        if i > 0:
            wobble = 0.06 * math.sin(seed + i * 0.9)
            buffered = buffered.buffer(width * wobble, quad_segs=6).buffer(-width * wobble * 0.55, quad_segs=6)
        buffered = buffered.buffer(width * 0.05, quad_segs=4).buffer(-width * 0.035, quad_segs=4)
        if valley is not None:
            buffered = buffered.intersection(valley)
        if buffered.is_empty:
            buffered = river_line.buffer(width)
        # Back to WGS84
        geom = _transform_geometry(
            buffered,
            lambda x, y: from_metric(x, y, lon0, lat0),
        )
        area_km2 = (
            geom.area
            * metres_per_deg_lon(lat0)
            * METRES_PER_DEG_LAT
            / 1_000_000
        )
        frames.append(
            {
                "t": hour,
                "label": format_hour(hour),
                "areaKm2": round(area_km2, 1),
                "geometry": mapping(geom),
            }
        )
    return frames


def format_hour(value: float) -> str:
    hour = int(value)
    minute = int(round((value - hour) * 60))
    return f"{hour:02d}:{minute:02d}"


def feature(geometry: BaseGeometry | dict, properties: dict | None = None) -> dict:
    geom = mapping(geometry) if isinstance(geometry, BaseGeometry) else geometry
    return {"type": "Feature", "geometry": geom, "properties": properties or {}}


def feature_collection(features: Iterable[dict]) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def polygon_coords(geometry: dict) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return [ring for poly in geometry["coordinates"] for ring in poly]
    return []


def simplify_geometry(geometry: dict, tolerance: float = 0.00002) -> dict:
    return mapping(shape(geometry).simplify(tolerance, preserve_topology=True))
