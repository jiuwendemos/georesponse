import io
import json
import zipfile

from georesponse.assessment import write_assessment
from georesponse.exports import (
    arcgis_export,
    assessment_pdf,
    change_overlay_geojson,
    dispatch_csv,
    duck_creek_claim,
    export_geojson_bundle,
    field_order_pdf,
    findings_geojson,
    guidewire_claim_center,
    integrations_manifest,
    maximo_work_order,
    qgis_project,
    sap_maintenance_order,
)
from georesponse.ranking import rank_sites


def _assessment(scenario):
    ranked, _ = rank_sites(scenario["sites"], exclude={"S01"})
    return write_assessment(scenario, ranked, reviews={"S01": "rejected"}), ranked


def test_findings_geojson_has_review_status(scenario):
    assessment, _ = _assessment(scenario)
    payload = findings_geojson(scenario, assessment)
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == len(scenario["sites"])
    assert payload["features"][0]["properties"]["modelVersion"]


def test_change_overlay_has_every_frame(scenario):
    overlay = change_overlay_geojson(scenario)
    assert len(overlay["features"]) == len(scenario["timeline"]["frames"])


def test_geojson_bundle_is_zip(scenario):
    assessment, _ = _assessment(scenario)
    data = export_geojson_bundle(scenario, assessment)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
    assert {"findings.geojson", "change-overlay.geojson", "assessment.json", "provenance.json"} <= names


def test_pdfs_start_with_pdf_header(scenario):
    assessment, _ = _assessment(scenario)
    assert assessment_pdf(scenario, assessment).startswith(b"%PDF")
    assignments = {a["siteId"]: a["team"] for a in scenario["fieldOrder"]["assignments"]}
    assert field_order_pdf(scenario, assessment, assignments).startswith(b"%PDF")


def test_qgis_and_arcgis_exports(scenario):
    assessment, _ = _assessment(scenario)
    qgs = qgis_project(scenario, assessment)
    assert "<qgis" in qgs and "findings.geojson" in qgs
    data = arcgis_export(scenario, assessment)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert "feature-service.json" in archive.namelist()
        service = json.loads(archive.read("feature-service.json"))
    assert service["spatialReference"]["wkid"] == 4326


def test_claims_payloads_never_auto_approve(scenario):
    assessment, _ = _assessment(scenario)
    guidewire = guidewire_claim_center(assessment)
    duck = duck_creek_claim(assessment)
    assert guidewire["body"]["claim"]["adjusterRequired"] is True
    assert duck["payload"]["RequiresAdjuster"] is True
    assert "auto-approves" in guidewire["note"]


def test_field_system_adapters(scenario):
    site = scenario["sites"][0]
    maximo = maximo_work_order(scenario, site)
    sap = sap_maintenance_order(scenario, site)
    assert maximo["worktype"] == "INSPECTION"
    assert sap["OrderType"] == "PM01"
    assert "Human review" in sap["LongText"]


def test_dispatch_csv_and_integrations(scenario):
    assignments = {a["siteId"]: a["team"] for a in scenario["fieldOrder"]["assignments"]}
    csv = dispatch_csv(scenario, assignments)
    assert csv.splitlines()[0].startswith("team,site_id")
    assert "Team 1" in csv
    manifest = integrations_manifest()
    assert manifest["policies"]["autoApprove"] is False
    assert "Guidewire ClaimCenter" in manifest["claims"]
