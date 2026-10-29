from georesponse.geo import BBox, circle_polygon, make_flood_envelopes, metres_between, tile_grid


def test_bbox_area_and_contains():
    bbox = BBox.around(7.1, 50.545, 8.0, 5.0)
    assert 39.5 < bbox.area_km2 < 40.5
    assert bbox.contains(7.1, 50.545)
    assert not bbox.contains(0.0, 0.0)


def test_tile_grid_covers_bbox():
    bbox = BBox(7.0, 50.5, 7.1, 50.6)
    tiles = tile_grid(bbox, 512)
    assert len(tiles) > 1
    for tile in tiles:
        west, south, east, north = tile["bounds"]
        assert bbox.west <= west < east <= bbox.east + 1e-9
        assert bbox.south <= south < north <= bbox.north + 1e-9


def test_circle_radius_is_close():
    circle = circle_polygon(7.1, 50.545, 500, steps=48)
    lon, lat = circle.exterior.coords[0]
    assert 480 < metres_between((7.1, 50.545), (lon, lat)) < 520


def test_flood_envelopes_grow_and_stay_in_order():
    route = [[7.05, 50.53], [7.10, 50.542], [7.15, 50.55]]
    frames = make_flood_envelopes(route, hours=[12, 14, 16, 18], start_width_m=80, end_width_m=700)
    assert [f["label"] for f in frames] == ["12:00", "14:00", "16:00", "18:00"]
    areas = [f["areaKm2"] for f in frames]
    assert areas == sorted(areas)
    assert areas[-1] > areas[0] * 2
    assert frames[-1]["geometry"]["type"] in {"Polygon", "MultiPolygon"}
