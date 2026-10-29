from georesponse.pilot import (
    baseline_event,
    build_pilot_dashboard,
    default_pilot_history,
    false_positive_log,
    pilot_offer,
    precision_recall_report,
)


def test_baseline_and_history():
    baseline = baseline_event()
    assert baseline["modelVersion"] == "none"
    history = default_pilot_history()
    assert len(history) == 7
    assert history[0]["assessmentMinutes"] > history[1]["assessmentMinutes"]


def test_dashboard_summary():
    dashboard = build_pilot_dashboard()
    summary = dashboard["summary"]
    assert summary["events"] == 6
    assert 0.8 < summary["precision"] <= 1
    assert summary["analystHoursSaved"] > 0
    assert len(summary["accuracyTrend"]) == 6
    assert "Synthetic" in dashboard["disclaimer"]


def test_false_positive_log_has_reasons():
    log = false_positive_log()
    assert len(log) >= 5
    assert all(item["reason"] for item in log)
    assert {item["review"] for item in log} <= {"rejected", "flagged"}


def test_precision_recall_and_offer():
    report = precision_recall_report()
    assert report["perEvent"]
    assert report["modelVersion"]
    offer = pilot_offer()
    assert offer["title"] == "GeoResponse pilot in 90 days"
    assert offer["successMeasures"]
