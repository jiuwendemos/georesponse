import pytest

from georesponse.connectors import (
    AirbusConnector,
    CapellaConnector,
    ConnectorError,
    ICEYEConnector,
    LocalConnector,
    PlanetConnector,
    SentinelConnector,
    SentinelSARConnector,
    build_connector,
    fuse_optical_sar,
    ingest_manifest,
)


def test_local_connector_lists_and_fetches(tmp_path):
    source = tmp_path / "drone"
    source.mkdir()
    (source / "ortho.tif").write_bytes(b"fake")
    (source / "notes.txt").write_text("ignore", encoding="utf-8")
    connector = LocalConnector(source)
    assets = connector.list_assets(bbox=[7, 50, 7.1, 50.1])
    assert len(assets) == 1
    target = tmp_path / "copy.tif"
    connector.fetch(assets[0], target)
    assert target.read_bytes() == b"fake"


def test_commercial_connectors_are_dry_run():
    for connector in (PlanetConnector(), AirbusConnector(), ICEYEConnector(), CapellaConnector()):
        assets = connector.list_assets([7, 50, 7.1, 50.1], "2021-07-14", "2021-07-16")
        assert assets
        assert assets[0].meta["dryRun"] is True
        with pytest.raises(ConnectorError):
            connector.fetch(assets[0], "unused.tif")


def test_sentinel_connectors():
    optical = SentinelConnector(dry_run=True)
    sar = SentinelSARConnector(dry_run=True)
    assert optical.list_assets([7, 50, 7.1, 50.1], "2021-07-14", "2021-07-16")[0].resolution_m == 10
    assert sar.list_assets([7, 50, 7.1, 50.1], "2021-07-14", "2021-07-16")[0].sar is True


def test_connector_factory_and_manifest():
    connector = build_connector("sentinel-2", dry_run=True)
    manifest = ingest_manifest(connector, [7, 50, 7.1, 50.1], "2021-07-14", "2021-07-16")
    assert manifest["count"] == 1
    assert manifest["dryRun"] is True


def test_optical_sar_fusion_is_bounded():
    fused = fuse_optical_sar(0.8, 0.6)
    assert fused["score"] == pytest.approx(0.71)
    assert 0.9 < fused["confidence"] <= 0.99
