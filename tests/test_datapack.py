from pathlib import Path

from georesponse.config import DATA_DIR


def test_index_lists_three_scenarios(index):
    assert len(index["scenarios"]) == 3
    assert index["default"] == "ahr-2021-flood"
    assert all(entry["sites"] > 0 for entry in index["scenarios"])


def test_primary_scenario_contract(scenario):
    meta = scenario["meta"]
    assert meta["id"] == "ahr-2021-flood"
    assert 39.5 < meta["areaKm2"] < 40.5
    assert len(scenario["sites"]) == 18
    assert len(scenario["timeline"]["frames"]) == 13
    assert meta["imagery"]["simulated"] is True
    assert meta["model"]


def test_all_sites_are_in_the_bbox(scenario):
    west, south, east, north = scenario["meta"]["bbox"]
    for site in scenario["sites"]:
        assert west <= site["lon"] <= east
        assert south <= site["lat"] <= north
        assert site["severity"] in {"red", "orange", "yellow"}
        assert site["riskAt"] > 0
        assert 0 <= site["confidence"] <= 1


def test_false_positive_is_top_ranked_then_reordered(scenario):
    assert scenario["falsePositive"]["siteId"] == "S01"
    assert scenario["ranking"][0]["id"] == "S01"
    assert scenario["rankingAfterReview"][0]["id"] == "S02"
    assert scenario["assessmentAfterReview"]["metrics"]["rejected"] == 1


def test_audience_choice_and_field_order(scenario):
    audience = scenario["audience"]
    assert audience["a"] and audience["b"]
    assert audience["a"]["id"] != audience["b"]["id"]
    assert audience["a"]["consequence"]
    order = scenario["fieldOrder"]
    assert len(order["assignments"]) == 3
    assert order["signature"].startswith("Analyst")


def test_map_layers_and_imagery_exist(scenario):
    base = Path(DATA_DIR)
    assert (base / scenario["map"]["basemap"]["file"].replace("data/", "")).exists()
    assert (base / scenario["imageryPair"]["before"].replace("data/", "")).exists()
    assert (base / scenario["imageryPair"]["after"].replace("data/", "")).exists()
    for site in scenario["sites"]:
        assert (base / site["evidence"]["before"].replace("data/", "")).exists()
        assert (base / site["evidence"]["after"].replace("data/", "")).exists()
    assert len(scenario["map"]["roads"]["features"]) > 5
    assert len(scenario["map"]["buildings"]["features"]) > 100
    assert scenario["map"]["landuse"]["features"]
    assert scenario["map"]["power"]["features"]


def test_timeline_is_deterministic_and_monotonic(scenario):
    areas = [frame["areaKm2"] for frame in scenario["timeline"]["frames"]]
    assert areas == sorted(areas)
    assert areas[-1] > 10
    assert scenario["timeline"]["frames"][0]["label"] == "12:00"


def test_provenance_sheet(scenario):
    provenance = scenario["provenance"]
    assert provenance["imagery"]["simulated"] is True
    assert any("Sentinel" in right for right in provenance["dataRights"])
    assert any("OpenStreetMap" in right for right in provenance["dataRights"])
    assert "human" in provenance["disclaimer"].lower()
