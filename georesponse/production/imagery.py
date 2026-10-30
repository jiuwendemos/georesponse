"""Live Sentinel-2 STAC search and windowed COG download.

This is the real imagery path: Earth Search STAC -> Sentinel-2 L2A COG ->
windowed read for the requested bbox -> local PNG cache.  No credentials are
needed for Sentinel-2; attribution is mandatory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds
except Exception:  # pragma: no cover - optional dependency
    rasterio = None  # type: ignore
    from_bounds = None  # type: ignore

from .config import ImagerySettings, get_settings


class ImageryUnavailable(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=90, headers={"User-Agent": "GeoResponse/0.2 (offline-capable decision support)"})


def search_sentinel(
    bbox: list[float],
    start: str,
    end: str,
    *,
    max_cloud: float = 30,
    limit: int = 20,
    settings: ImagerySettings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings().imagery
    body = {
        "collections": [settings.collection],
        "bbox": bbox,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": limit,
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
    }
    with _client() as client:
        response = client.post(settings.stac_url.rstrip("/") + "/search", json=body)
        response.raise_for_status()
        payload = response.json()
    full: list[dict] = []
    partial: list[dict] = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        visual = feature.get("assets", {}).get("visual") or feature.get("assets", {}).get("thumbnail")
        if not visual:
            continue
        fb = feature.get("bbox")
        covers = bool(fb and fb[0] <= bbox[0] and fb[1] <= bbox[1] and fb[2] >= bbox[2] and fb[3] >= bbox[3])
        item = (
            {
                "id": feature["id"],
                "datetime": props.get("datetime"),
                "cloud": float(props.get("eo:cloud_cover", 100)),
                "platform": props.get("platform"),
                "bbox": feature.get("bbox"),
                "visual": visual.get("href"),
                "collection": settings.collection,
                "stac": f"{settings.stac_url.rstrip('/')}/collections/{settings.collection}/items/{feature['id']}",
                "license": "Copernicus Sentinel data — free and open, attribution required",
            }
        )
        (full if covers else partial).append(item)
    items = full or partial
    return sorted(items, key=lambda item: (item["cloud"], item["datetime"] or ""))


def pick_pair(items: list[dict], split: str) -> tuple[dict | None, dict | None, list[dict]]:
    before = [item for item in items if (item["datetime"] or "") < split]
    after = [item for item in items if (item["datetime"] or "") >= split]
    return (before[0] if before else None, after[0] if after else None, items)


def fetch_visual(item: dict, bbox: list[float], out_path: str | Path, *, width: int = 1600, height: int = 1000) -> dict:
    if rasterio is None or from_bounds is None:
        raise ImageryUnavailable("rasterio is required for COG windows")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(item["visual"]) as dataset:
        left, bottom, right, top = transform_bounds("EPSG:4326", dataset.crs, *bbox)
        window = from_bounds(left, bottom, right, top, dataset.transform)
        data = dataset.read(
            [1, 2, 3],
            window=window,
            out_shape=(3, height, width),
            boundless=True,
            resampling=Resampling.bilinear,
        )
        rgb = np.transpose(data, (1, 2, 0)).astype(np.uint8)
        Image.fromarray(rgb).save(out_path, optimize=True)
        meta = {
            "id": item["id"],
            "datetime": item["datetime"],
            "cloud": item["cloud"],
            "platform": item.get("platform"),
            "crs": str(dataset.crs),
            "source": item.get("visual"),
            "stac": item.get("stac"),
            "license": item.get("license"),
            "bbox": bbox,
            "file": str(out_path),
            "width": width,
            "height": height,
        }
        out_path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta


def fetch_pair(
    bbox: list[float],
    start: str,
    split: str,
    end: str,
    *,
    out_dir: str | Path,
    name: str,
    max_cloud: float = 30,
    width: int = 1600,
    height: int = 1000,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = search_sentinel(bbox, start, end, max_cloud=max_cloud)
    before, after, all_items = pick_pair(items, split)
    if not before or not after:
        raise ImageryUnavailable(f"no usable Sentinel-2 pair in {start}..{end} (matched {len(items)})")
    before_meta = fetch_visual(before, bbox, out_dir / f"{name}-before.png", width=width, height=height)
    after_meta = fetch_visual(after, bbox, out_dir / f"{name}-after.png", width=width, height=height)
    manifest = {
        "name": name,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bbox": bbox,
        "before": before_meta,
        "after": after_meta,
        "candidates": len(all_items),
        "attribution": "© Copernicus Sentinel data — free and open, attribution required",
        "simulated": False,
    }
    (out_dir / f"{name}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


SCENARIOS = {
    "ahr-2021-flood": {
        "bbox": [7.043, 50.522, 7.157, 50.567],
        "start": "2021-07-01",
        "split": "2021-07-14",
        "end": "2021-07-31",
        "name": "ahr-2021-flood",
    },
    "eifel-2022-wildfire": {
        "bbox": [6.35, 50.54, 6.49, 50.65],
        "start": "2022-05-15",
        "split": "2022-07-25",
        "end": "2022-10-15",
        "name": "eifel-2022-wildfire",
    },
    "cologne-2024-construction": {
        "bbox": [6.84, 50.89, 6.97, 50.98],
        "start": "2024-01-01",
        "split": "2024-03-12",
        "end": "2024-06-30",
        "name": "cologne-2024-construction",
    },
}


def fetch_scenario(scenario_id: str, out_dir: str | Path = "runtime/imagery") -> dict:
    config = SCENARIOS.get(scenario_id)
    if not config:
        raise KeyError(scenario_id)
    return fetch_pair(
        config["bbox"],
        config["start"],
        config["split"],
        config["end"],
        out_dir=Path(out_dir) / scenario_id,
        name=config["name"],
    )


def cache_status(scenario_id: str, cache_dir: str | Path = "runtime/imagery") -> dict:
    path = Path(cache_dir) / scenario_id / f"{scenario_id}.json"
    if not path.exists():
        return {"scenario": scenario_id, "cached": False, "path": str(path)}
    return {"scenario": scenario_id, "cached": True, "path": str(path), "manifest": json.loads(path.read_text(encoding="utf-8"))}
