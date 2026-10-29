from fastapi.testclient import TestClient

from georesponse.api import app

client = TestClient(app)


def test_health_and_scenarios():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    index = client.get("/api/scenarios")
    assert index.status_code == 200
    assert index.json()["default"] == "ahr-2021-flood"


def test_scenario_and_assessment():
    response = client.get("/api/scenarios/ahr-2021-flood")
    assert response.status_code == 200
    assert len(response.json()["sites"]) == 18
    assessment = client.post("/api/scenarios/ahr-2021-flood/assessment", json={"reviews": {"S01": "rejected"}, "teams": 3})
    assert assessment.status_code == 200
    data = assessment.json()
    assert data["metrics"]["rejected"] == 1
    assert data["findings"][0]["id"] == "S02"


def test_exports_and_integrations():
    assert client.get("/api/scenarios/ahr-2021-flood/exports/geojson").status_code == 200
    assert client.get("/api/scenarios/ahr-2021-flood/assessment.pdf").content.startswith(b"%PDF")
    assert client.get("/api/scenarios/ahr-2021-flood/field-order.pdf").content.startswith(b"%PDF")
    assert client.get("/api/scenarios/ahr-2021-flood/qgis").status_code == 200
    assert client.get("/api/scenarios/ahr-2021-flood/dispatch.csv").status_code == 200
    assert client.get("/api/scenarios/ahr-2021-flood/claims/guidewire").json()["body"]["claim"]["adjusterRequired"] is True
    assert client.get("/api/scenarios/ahr-2021-flood/work/maximo/S02").json()["worktype"] == "INSPECTION"


def test_unknown_scenario_is_404():
    assert client.get("/api/scenarios/nope").status_code == 404


def test_dashboard_and_audit():
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/api/monitoring").status_code == 200
    assert client.get("/api/integrations").status_code == 200
    assert client.get("/api/privacy").status_code == 200
    created = client.post(
        "/api/audit",
        json={"action": "review.approved", "siteId": "S02", "analyst": "Test Analyst"},
    )
    assert created.status_code == 200
    listed = client.get("/api/audit").json()
    assert listed["verified"] is True
