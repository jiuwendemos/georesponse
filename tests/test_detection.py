import numpy as np

from georesponse.detection import (
    analyse_tile,
    change_map,
    classify_change_type,
    classify_severity,
    cloud_cover,
    confidence_from_change,
    detect_pair,
    load_rgb,
    ndvi_delta,
    save_rgb,
    tile_geotiff,
    tile_raster,
)
from georesponse.geo import BBox


def test_cloud_cover_detects_bright_pixels():
    clear = np.zeros((20, 20, 3), dtype=np.float32)
    clear[:] = (0.2, 0.4, 0.3)
    cloudy = clear.copy()
    cloudy[:10, :10] = 0.98
    assert cloud_cover(clear) == 0
    assert cloud_cover(cloudy) > 0.2


def test_change_map_and_confidence():
    before = np.zeros((32, 32, 3), dtype=np.float32)
    after = before.copy()
    after[8:24, 8:24] = 0.8
    mask = change_map(before, after)
    assert mask.mean() > 0.2
    assert confidence_from_change(mask.mean(), 0.5) > confidence_from_change(0.01, 0.01)


def test_change_type_flood_and_burn():
    before = np.zeros((16, 16, 3), dtype=np.float32)
    after_flood = before.copy()
    after_flood[:, :, 2] = 0.8
    after_flood[:, :, 0] = 0.1
    mask = np.ones((16, 16), dtype=bool)
    assert classify_change_type(before, after_flood, mask) == "flood"
    after_burn = before.copy()
    after_burn[:, :, 1] = 0.05
    after_burn[:, :, 0] = 0.2
    assert classify_change_type(before, after_burn, mask) == "burn"


def test_severity_bands():
    assert classify_severity(0.9, 0.95) == "red"
    assert classify_severity(0.35, 0.7) == "orange"
    assert classify_severity(0.02, 0.4) == "yellow"


def test_analyse_tile_contract():
    before = np.zeros((16, 16, 3), dtype=np.float32)
    after = before.copy()
    after[4:12, 4:12] = 0.5
    result = analyse_tile(before, after, tile_id="r00c00", row=0, col=0, bounds=[0, 0, 1, 1])
    assert result.id == "r00c00"
    assert 0 <= result.confidence <= 1
    assert result.severity in {"red", "orange", "yellow"}


def test_raster_tiling(tmp_path):
    array = np.random.default_rng(2).random((64, 96, 3)).astype(np.float32)
    assert len(list(tile_raster(array, 32))) == 6
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    save_rgb(array, before)
    changed = array.copy()
    changed[32:, 32:] = 0.9
    save_rgb(changed, after)
    results = detect_pair(before, after, bbox=BBox(0, 0, 0.01, 0.01), tile_size=32)
    assert results
    assert all("severity" in row for row in results)


def test_geotiff_fallback_tiles_png_with_sidecar(tmp_path, monkeypatch):
    import georesponse.detection as detection

    monkeypatch.setattr(detection, "HAVE_RASTERIO", False)
    raster = tmp_path / "scene.png"
    save_rgb(np.random.default_rng(3).random((64, 64, 3)).astype(np.float32), raster)
    (tmp_path / "scene.json").write_text('{"bbox": [7.0, 50.5, 7.1, 50.6]}', encoding="utf-8")
    source = tmp_path / "scene.tif"  # no rasterio in the normal test path
    manifest = tile_geotiff(source, tmp_path / "tiles", tile_size=32)
    assert manifest["engine"] == "pillow-fallback"
    assert manifest["tiles"]
    assert (tmp_path / "tiles" / "manifest.json").exists()


def test_ndvi_delta_sign():
    before = np.zeros((8, 8, 3), dtype=np.float32) + 0.5
    after = before + 0.1
    assert ndvi_delta(before, after) > 0
    assert ndvi_delta(after, before) < 0
    assert load_rgb  # imported symbol is available


def test_sar_change_detection():
    from georesponse.detection import detect_sar_change

    before = np.full((16, 16), -12.0)
    after = before.copy()
    after[4:12, 4:12] = -6.0
    result = detect_sar_change(before, after, threshold_db=3.0)
    assert result["fraction"] == 0.25
    assert result["meanDeltaDb"] > 1
    assert 0.45 < result["confidence"] < 1
    quiet = detect_sar_change(before, before)
    assert quiet["fraction"] == 0
    assert quiet["changeType"] == "none"
