"""Imagery connectors.

Each connector exposes the same three verbs — ``list_assets``, ``fetch`` and
``health`` — so the pipeline does not care whether the source is Sentinel-2,
Planet, Maxar, Airbus, Sentinel-1 SAR or a customer drone folder.  Network
connectors are dry-run by default and never run during the stage demo.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class ImageryAsset:
    id: str
    source: str
    acquired: str
    bbox: list[float]
    resolution_m: float
    path: str | None = None
    cloud_cover: float | None = None
    sar: bool = False
    meta: dict = field(default_factory=dict)


class ConnectorError(RuntimeError):
    pass


class ImageryConnector:
    name = "base"
    requires_network = False

    def __init__(self, *, dry_run: bool = True, config: dict | None = None) -> None:
        self.dry_run = dry_run
        self.config = config or {}

    def health(self) -> dict:
        return {"connector": self.name, "dryRun": self.dry_run, "network": self.requires_network}

    def list_assets(self, bbox: list[float], start: str, end: str) -> list[ImageryAsset]:
        raise NotImplementedError

    def fetch(self, asset: ImageryAsset, destination: str | Path) -> Path:
        if asset.path:
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(asset.path).read_bytes())
            return destination
        if self.dry_run:
            raise ConnectorError(f"{self.name}: dry run, no credentials used")
        raise ConnectorError(f"{self.name}: production credentials are not configured")


class LocalConnector(ImageryConnector):
    """Ingests a folder of GeoTIFF/PNG/LAS files (customer drone or archive)."""

    name = "local"
    SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".las", ".laz"}

    def __init__(self, root: str | Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = Path(root)

    def list_assets(self, bbox: list[float] | None = None, start: str = "", end: str = "") -> list[ImageryAsset]:
        if not self.root.exists():
            return []
        assets = []
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in self.SUFFIXES or not path.is_file():
                continue
            stat = path.stat()
            acquired = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
            assets.append(
                ImageryAsset(
                    id=path.stem,
                    source="local",
                    acquired=acquired,
                    bbox=bbox or [-180, -90, 180, 90],
                    resolution_m=0.1 if path.suffix.lower() in {".las", ".laz"} else 0.5,
                    path=str(path),
                    sar=path.suffix.lower() in {".tif", ".tiff"} and "sar" in path.name.lower(),
                )
            )
        return assets


class SentinelConnector(ImageryConnector):
    """Sentinel-2 L2A via the Copernicus STAC catalogue."""

    name = "sentinel-2"
    requires_network = True
    STAC = "https://catalogue.dataspace.copernicus.eu/stac/v1/search"

    def list_assets(self, bbox: list[float], start: str, end: str) -> list[ImageryAsset]:
        if self.dry_run:
            return [
                ImageryAsset(
                    id="S2B_MSIL2A_20210714T103029_demo",
                    source="Sentinel-2",
                    acquired="2021-07-14T10:30:29Z",
                    bbox=bbox,
                    resolution_m=10,
                    cloud_cover=0.18,
                    meta={"collection": "sentinel-2-l2a", "dryRun": True, "stac": self.STAC},
                )
            ]
        raise ConnectorError("Sentinel STAC live pull requires network; use build-demo offline")


class SentinelSARConnector(ImageryConnector):
    name = "sentinel-1"
    requires_network = True

    def list_assets(self, bbox: list[float], start: str, end: str) -> list[ImageryAsset]:
        return [
            ImageryAsset(
                id="S1A_IW_GRDH_20210714_demo",
                source="Sentinel-1 SAR",
                acquired="2021-07-14T05:42:00Z",
                bbox=bbox,
                resolution_m=10,
                sar=True,
                meta={"polarisation": "VV+VH", "dryRun": True},
            )
        ]


class CommercialConnector(ImageryConnector):
    requires_network = True
    resolve_m = 3.0

    def list_assets(self, bbox: list[float], start: str, end: str) -> list[ImageryAsset]:
        return [
            ImageryAsset(
                id=f"{self.name}-{start[:10]}-demo",
                source=self.name,
                acquired=f"{start}T09:15:00Z",
                bbox=bbox,
                resolution_m=self.resolve_m,
                cloud_cover=0.11,
                meta={"dryRun": self.dry_run, "licence": "commercial — not for public stage without clearance"},
            )
        ]


class PlanetConnector(CommercialConnector):
    name = "Planet"
    resolve_m = 3.0


class MaxarConnector(CommercialConnector):
    name = "Maxar"
    resolve_m = 0.3


class AirbusConnector(CommercialConnector):
    name = "Airbus"
    resolve_m = 0.5


class ICEYEConnector(CommercialConnector):
    name = "ICEYE"
    resolve_m = 1.0

    def list_assets(self, bbox, start, end):  # type: ignore[override]
        assets = super().list_assets(bbox, start, end)
        for asset in assets:
            asset.sar = True
        return assets


class CapellaConnector(CommercialConnector):
    name = "Capella"
    resolve_m = 0.5

    def list_assets(self, bbox, start, end):  # type: ignore[override]
        assets = super().list_assets(bbox, start, end)
        for asset in assets:
            asset.sar = True
        return assets


def build_connector(name: str, *, root: str | Path | None = None, dry_run: bool = True) -> ImageryConnector:
    table = {
        "local": lambda: LocalConnector(root or ".", dry_run=dry_run),
        "sentinel-2": lambda: SentinelConnector(dry_run=dry_run),
        "sentinel-1": lambda: SentinelSARConnector(dry_run=dry_run),
        "planet": lambda: PlanetConnector(dry_run=dry_run),
        "maxar": lambda: MaxarConnector(dry_run=dry_run),
        "airbus": lambda: AirbusConnector(dry_run=dry_run),
        "iceye": lambda: ICEYEConnector(dry_run=dry_run),
        "capella": lambda: CapellaConnector(dry_run=dry_run),
    }
    if name not in table:
        raise ConnectorError(f"unknown connector: {name}")
    return table[name]()


def ingest_manifest(connector: ImageryConnector, bbox: list[float], start: str, end: str) -> dict:
    assets = connector.list_assets(bbox, start, end)
    return {
        "connector": connector.name,
        "dryRun": connector.dry_run,
        "count": len(assets),
        "assets": [asset.__dict__ for asset in assets],
    }


def watch_folder(root: str | Path, callback, *, poll_seconds: int = 5) -> None:  # pragma: no cover - loop
    """New file → pipeline trigger.  Production uses a queue; this is the edge demo."""
    import time

    root = Path(root)
    seen: set[str] = set()
    while True:
        connector = LocalConnector(root)
        for asset in connector.list_assets():
            if asset.id not in seen:
                seen.add(asset.id)
                callback(asset)
        time.sleep(poll_seconds)


def fuse_optical_sar(optical_change: float, sar_change: float, *, optical_weight: float = 0.55) -> dict:
    """Late fusion of optical and SAR change scores."""
    score = optical_weight * optical_change + (1 - optical_weight) * sar_change
    return {
        "score": round(score, 4),
        "optical": round(optical_change, 4),
        "sar": round(sar_change, 4),
        "method": "weighted late fusion",
        "confidence": round(min(0.99, 0.55 + score * 0.9), 3),
    }


def load_connector_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
