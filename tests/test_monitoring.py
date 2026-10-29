from georesponse.monitoring import anomaly_score, baseline_series, build_monitoring_pack, evaluate_region, monitor_regions


def test_baseline_and_anomaly():
    baseline = baseline_series([0.04, 0.05, 0.03, 0.06, 0.05, 0.04])
    assert baseline["n"] == 6
    assert anomaly_score(0.3, baseline) > 5
    assert anomaly_score(0.05, baseline) < 1


def test_alert_requires_both_sigma_and_absolute_change():
    hot = evaluate_region("AHR", 0.31, [0.04, 0.05, 0.03, 0.06])
    quiet = evaluate_region("BON", 0.05, [0.04, 0.05, 0.03, 0.06])
    assert hot["alert"] is True
    assert hot["severity"] == "red"
    assert quiet["alert"] is False


def test_monitor_regions_and_pack():
    regions = [
        {"id": "A", "observedChange": 0.3, "history": [0.02, 0.03, 0.02]},
        {"id": "B", "observedChange": 0.03, "history": [0.02, 0.03, 0.02]},
    ]
    alerts = monitor_regions(regions)
    assert len(alerts) == 2
    pack = build_monitoring_pack(regions)
    assert pack["summary"]["regions"] == 2
    assert pack["summary"]["alerts"] == 1
