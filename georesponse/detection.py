"""Imagery tiling, cloud screening and change detection.

The production path reads GeoTIFFs with rasterio.  A PIL/PNG fallback keeps the
demo and the test-suite fully offline and dependency-light.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image

from .config import CLOUD_LIMIT, TILE_SIZE
from .geo import BBox, tile_grid

try:  # pragma: no cover - optional native path
    import rasterio
    from rasterio.windows import Window

    HAVE_RASTERIO = True
except Exception:  # pragma: no cover
    rasterio = None  # type: ignore
    Window = None  # type: ignore
    HAVE_RASTERIO = False


@dataclass
class TileResult:
    id: str
    row: int
    col: int
    bounds: list[float]
    change_fraction: float
    mean_delta: float
    confidence: float
    severity: str
    cloud: float
    change_type: str = "change"

    def to_dict(self) -> dict:
        return asdict(self)


def load_rgb(path: str | Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def save_rgb(array: np.ndarray, path: str | Path) -> None:
    data = np.clip(array * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(data, mode="RGB").save(path)


def cloud_cover(array: np.ndarray) -> float:
    """Fraction of very bright, low-saturation pixels (a conservative proxy).

    Real ingestion should prefer the Sentinel-2 scene classification layer; this
    estimator is deliberately simple so the rule is auditable offline.
    """
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError("expected HxWx3 RGB array")
    rgb = np.clip(array, 0, 1)
    brightness = rgb.mean(axis=2)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    return float(np.mean((brightness > 0.86) & (saturation < 0.08)))


def change_map(before: np.ndarray, after: np.ndarray, threshold: float = 0.12) -> np.ndarray:
    if before.shape != after.shape:
        raise ValueError("before/after rasters must have the same shape")
    delta = np.abs(after - before).mean(axis=2)
    return delta > threshold


def confidence_from_change(fraction: float, mean_delta: float, cloud: float = 0.0) -> float:
    """Calibrated-looking confidence in [0, 1] from observable evidence."""
    signal = 1.0 - np.exp(-(fraction * 9.0 + mean_delta * 5.0))
    penalty = min(0.45, cloud * 1.3)
    return float(np.clip(0.42 + 0.56 * signal - penalty, 0.05, 0.995))


def classify_severity(fraction: float, confidence: float) -> str:
    score = 0.62 * min(1.0, fraction * 2.0) + 0.38 * confidence
    if score >= 0.72:
        return "red"
    if score >= 0.45:
        return "orange"
    return "yellow"


def classify_change_type(before: np.ndarray, after: np.ndarray, mask: np.ndarray) -> str:
    if not mask.any():
        return "none"
    b = before[mask]
    a = after[mask]
    delta = a - b
    blue = float(delta[:, 2].mean() - delta[:, 0].mean())
    green = float(delta[:, 1].mean() - delta[:, 0].mean())
    darkening = float((a.mean() - b.mean()))
    if blue > 0.01:
        return "flood"
    if green < -0.015:
        return "burn"
    if darkening < -0.02:
        return "structure"
    return "construction"


def analyse_tile(
    before: np.ndarray,
    after: np.ndarray,
    *,
    tile_id: str,
    row: int,
    col: int,
    bounds: list[float],
    threshold: float = 0.12,
) -> TileResult:
    cloud = cloud_cover(after)
    mask = change_map(before, after, threshold)
    fraction = float(mask.mean())
    delta = float(np.abs(after - before).mean())
    confidence = confidence_from_change(fraction, delta, cloud)
    return TileResult(
        id=tile_id,
        row=row,
        col=col,
        bounds=bounds,
        change_fraction=round(fraction, 5),
        mean_delta=round(delta, 5),
        confidence=round(confidence, 4),
        severity=classify_severity(fraction, confidence),
        cloud=round(cloud, 4),
        change_type=classify_change_type(before, after, mask),
    )


def tile_raster(array: np.ndarray, size: int = TILE_SIZE) -> Iterator[tuple[int, int, np.ndarray]]:
    height, width = array.shape[:2]
    for row, y in enumerate(range(0, height, size)):
        for col, x in enumerate(range(0, width, size)):
            yield row, col, array[y : y + size, x : x + size]


def detect_pair(
    before_path: str | Path,
    after_path: str | Path,
    *,
    bbox: BBox | None = None,
    tile_size: int = TILE_SIZE,
    cloud_limit: float = CLOUD_LIMIT,
) -> list[dict]:
    """Tile a before/after pair, screen clouds and return change findings."""
    before = load_rgb(before_path)
    after = load_rgb(after_path)
    boxes = tile_grid(bbox, tile_size) if bbox else []
    results: list[dict] = []
    for row, col, tile in tile_raster(before, tile_size):
        a_tile = after[
            row * tile_size : row * tile_size + tile.shape[0],
            col * tile_size : col * tile_size + tile.shape[1],
        ]
        if a_tile.shape != tile.shape:
            continue
        index = row * 1000 + col
        bounds = boxes[index]["bounds"] if index < len(boxes) else [0.0, 0.0, 0.0, 0.0]
        result = analyse_tile(
            tile,
            a_tile,
            tile_id=f"r{row:02d}c{col:02d}",
            row=row,
            col=col,
            bounds=bounds,
        )
        if result.cloud > cloud_limit:
            continue
        results.append(result.to_dict())
    return results


def ndvi_delta(before: np.ndarray, after: np.ndarray) -> float:
    """NDVI change without a red/NIR band pair: a documented greenness proxy."""
    b = before.mean(axis=2)
    a = after.mean(axis=2)
    return float(np.mean(a - b))


def write_detection_manifest(results: list[dict], path: str | Path, meta: dict | None = None) -> None:
    payload = {"meta": meta or {}, "tiles": results}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# GeoTIFF tiling engine
# ---------------------------------------------------------------------------


def tile_geotiff(
    source: str | Path,
    out_dir: str | Path,
    *,
    tile_size: int = TILE_SIZE,
    max_tiles: int = 64,
    reproject_to: str = "EPSG:4326",
) -> dict:
    """Split a GeoTIFF into PNG tiles and a manifest with WGS84 bounds.

    Uses rasterio when installed.  When it is not, an accompanying ``.json``
    sidecar with a bbox and a PNG of the same stem is accepted, which keeps the
    pipeline runnable on a laptop without GDAL.
    """
    source = Path(source)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if HAVE_RASTERIO and source.suffix.lower() in {".tif", ".tiff"}:
        return _tile_geotiff_rasterio(source, out_dir, tile_size, max_tiles, reproject_to)
    return _tile_geotiff_fallback(source, out_dir, tile_size, max_tiles)


def _tile_geotiff_rasterio(  # pragma: no cover - requires rasterio
    source: Path,
    out_dir: Path,
    tile_size: int,
    max_tiles: int,
    reproject_to: str,
) -> dict:
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(source) as dataset:
        transform, width, height = calculate_default_transform(
            dataset.crs, reproject_to, dataset.width, dataset.height, *dataset.bounds
        )
        data = np.zeros((dataset.count, height, width), dtype=dataset.dtypes[0])
        reproject(
            source=rasterio.band(dataset, list(range(1, dataset.count + 1))),
            destination=data,
            src_transform=dataset.transform,
            src_crs=dataset.crs,
            dst_transform=transform,
            dst_crs=reproject_to,
            resampling=Resampling.bilinear,
        )
        bounds = rasterio.transform.array_bounds(height, width, transform)
        bbox = BBox(bounds[0], bounds[1], bounds[2], bounds[3])
        tiles = tile_grid(bbox, tile_size)
        manifest: list[dict] = []
        for row in range(0, height, tile_size):
            for col in range(0, width, tile_size):
                if len(manifest) >= max_tiles:
                    break
                window = Window(col, row, min(tile_size, width - col), min(tile_size, height - row))
                tile_transform = rasterio.windows.transform(window, transform)
                tile_bounds = rasterio.transform.array_bounds(window.height, window.width, tile_transform)
                name = f"r{row // tile_size:03d}c{col // tile_size:03d}.png"
                rgb = np.transpose(data[:3, window.row_off : window.row_off + window.height,
                                         window.col_off : window.col_off + window.width], (1, 2, 0))
                if rgb.dtype != np.uint8:
                    rgb = (rgb / max(1.0, float(rgb.max())) * 255).astype(np.uint8)
                Image.fromarray(rgb).save(out_dir / name)
                manifest.append(
                    {
                        "file": name,
                        "bounds": list(tile_bounds),
                        "row": row // tile_size,
                        "col": col // tile_size,
                    }
                )
    payload = {
        "source": str(source),
        "crs": reproject_to,
        "tileSize": tile_size,
        "tiles": manifest,
        "engine": "rasterio",
    }
    (out_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _tile_geotiff_fallback(source: Path, out_dir: Path, tile_size: int, max_tiles: int) -> dict:
    sidecar = source.with_suffix(".json")
    image_path = source if source.suffix.lower() in {".png", ".jpg", ".jpeg"} else source.with_suffix(".png")
    if not image_path.exists():
        raise FileNotFoundError(f"no GeoTIFF reader available and no raster found for {source}")
    bbox_data = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    bbox = BBox(*bbox_data["bbox"]) if "bbox" in bbox_data else BBox(-180, -90, 180, 90)
    image = Image.open(image_path).convert("RGB")
    manifest: list[dict] = []
    boxes = tile_grid(bbox, 512)
    for row, y in enumerate(range(0, image.height, tile_size)):
        for col, x in enumerate(range(0, image.width, tile_size)):
            if len(manifest) >= max_tiles:
                break
            crop = image.crop((x, y, min(x + tile_size, image.width), min(y + tile_size, image.height)))
            name = f"r{row:03d}c{col:03d}.png"
            crop.save(out_dir / name)
            index = row * 1000 + col
            manifest.append(
                {
                    "file": name,
                    "bounds": boxes[index]["bounds"] if index < len(boxes) else bbox.as_list(),
                    "row": row,
                    "col": col,
                }
            )
    payload = {
        "source": str(source),
        "crs": "EPSG:4326",
        "tileSize": tile_size,
        "tiles": manifest,
        "engine": "pillow-fallback",
        "note": "Install rasterio for native GeoTIFF + arbitrary CRS support.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
