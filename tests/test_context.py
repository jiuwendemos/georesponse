from georesponse.context import ContextPack, Asset, enrich_site, match_insured_property, road_access_status


def test_context_helpers():
    context = ContextPack(
        roads=[{"name": "B267", "class": "primary", "coords": [[7.1, 50.545], [7.11, 50.546]]}],
        buildings=[],
        assets=[Asset(id="AST-1", name="Substation", kind="substation", lon=7.1, lat=50.545, value_eur=1000)],
        population=[{"lon": 7.1, "lat": 50.545, "people": 500}],
    )
    road = context.nearest_road(7.1, 50.545)
    assert road and road["name"] == "B267"
    assert context.population_near(7.1, 50.545) == 500
    assert context.assets_near(7.1, 50.545)[0].name == "Substation"


def test_enrich_site_adds_why_chain():
    context = ContextPack(
        roads=[{"name": "B267", "class": "primary", "coords": [[7.1, 50.545]]}],
        assets=[Asset(id="AST-1", name="Substation", kind="substation", lon=7.1, lat=50.545)],
        population=[{"lon": 7.1, "lat": 50.545, "people": 700}],
    )
    site = {"id": "S99", "name": "Test", "lon": 7.1, "lat": 50.545, "valueEur": 1, "severity": "red"}
    enriched = enrich_site(site, context, [])
    assert {item["label"] for item in enriched["why"]} == {"Access", "Power", "People"}


def test_insured_property_match():
    policies = [{"id": "POL-1", "bbox": [7.0, 50.5, 7.2, 50.6], "lon": 7.1, "lat": 50.55}]
    assert match_insured_property(7.1, 50.55, policies)["id"] == "POL-1"
    assert match_insured_property(8.0, 49.0, policies) is None


def test_road_access_status():
    road = {"geometry": {"type": "LineString", "coordinates": [[7.0, 50.0], [7.1, 50.0]]}}
    flood = [{"type": "Polygon", "coordinates": [[[7.0, 49.9], [7.1, 49.9], [7.1, 50.1], [7.0, 50.1], [7.0, 49.9]]]}]
    assert road_access_status(road, flood) in {"blocked", "flooded"}
    assert road_access_status(road, []) == "clear"
