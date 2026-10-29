"""Exports and system integrations.

Everything here is a pure function over the scenario + assessment: GeoJSON,
PDF one-pager, QGIS project, ArcGIS package, claims payloads, Maximo/SAP CSVs.
No network calls are required, which is what makes the offline demo credible.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Iterable

from .config import PILOT
from .geo import feature, feature_collection

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    HAVE_REPORTLAB = True
except Exception:  # pragma: no cover
    canvas = None  # type: ignore
    HAVE_REPORTLAB = False


def findings_geojson(scenario: dict, assessment: dict) -> dict:
    features = []
    for site in scenario["sites"]:
        finding = next((f for f in assessment["findings"] if f["id"] == site["id"]), None)
        props = {
            "id": site["id"],
            "name": site["name"],
            "severity": site["severity"],
            "confidence": site["confidence"],
            "changeExtentM2": site["changeExtentM2"],
            "valueEur": site.get("valueEur", 0),
            "population": site.get("population", 0),
            "access": site["accessStatus"],
            "review": finding["review"] if finding else "pending",
            "rank": finding["rank"] if finding else None,
            "modelVersion": assessment["modelVersion"],
            "imagery": scenario["meta"]["imagery"]["source"],
            "simulated": scenario["meta"]["imagery"].get("simulated", True),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [site["lon"], site["lat"]]},
                "properties": props,
            }
        )
    return feature_collection(features)


def change_overlay_geojson(scenario: dict) -> dict:
    features = []
    for frame in scenario["timeline"]["frames"]:
        features.append(feature(frame["geometry"], {"t": frame["t"], "label": frame["label"], "areaKm2": frame["areaKm2"]}))
    return feature_collection(features)


def export_geojson_bundle(scenario: dict, assessment: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("findings.geojson", json.dumps(findings_geojson(scenario, assessment), indent=2))
        archive.writestr("change-overlay.geojson", json.dumps(change_overlay_geojson(scenario), indent=2))
        archive.writestr("assessment.json", json.dumps(assessment, indent=2))
        archive.writestr("provenance.json", json.dumps(scenario["meta"], indent=2))
    return buffer.getvalue()


def _draw_minimap(c: "canvas.Canvas", scenario: dict, x: float, y: float, width: float, height: float) -> None:
    bbox = scenario["meta"]["bbox"]
    west, south, east, north = bbox

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (x + (lon - west) / (east - west) * width, y + (lat - south) / (north - south) * height)

    c.setFillColor(colors.HexColor("#07131c"))
    c.rect(x, y, width, height, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#1f4c5c"))
    c.setLineWidth(0.3)
    for i in range(1, 5):
        c.line(x + width * i / 5, y, x + width * i / 5, y + height)
        c.line(x, y + height * i / 5, x + width, y + height * i / 5)

    # latest flood extent as a coarse bounding hint
    frames = scenario["timeline"]["frames"]
    if frames:
        import shapely.geometry as sg

        geom = sg.shape(frames[-1]["geometry"])
        if geom.geom_type == "Polygon":
            pts = [project(lon, lat) for lon, lat in geom.exterior.coords]
            c.setFillColor(colors.HexColor("#0e5b6e"), alpha=0.55)
            c.setStrokeColor(colors.HexColor("#22d3ee"))
            path = c.beginPath()
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            path.close()
            c.drawPath(path, fill=1, stroke=1)

    for site in scenario["sites"]:
        px, py = project(site["lon"], site["lat"])
        color = {"red": "#fb7185", "orange": "#fbbf24", "yellow": "#facc15"}[site["severity"]]
        c.setFillColor(colors.HexColor(color))
        c.circle(px, py, 2.6, fill=1, stroke=0)
        if site["id"] in scenario.get("heroSiteIds", []):
            c.setStrokeColor(colors.white)
            c.setLineWidth(0.6)
            c.circle(px, py, 6, fill=0, stroke=1)


def assessment_pdf(scenario: dict, assessment: dict) -> bytes:
    if not HAVE_REPORTLAB:  # pragma: no cover
        return json.dumps({"error": "reportlab not installed"}, indent=2).encode("utf-8")
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 42

    c.setFillColor(colors.HexColor("#0b1f2a"))
    c.rect(0, height - 92, width, 92, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - 48, "GeoResponse")
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#8fd8e6"))
    c.drawString(margin, height - 64, "AI analyst for imagery · human-signed assessment")
    c.drawRightString(width - margin, height - 48, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, height - 82, scenario["meta"]["title"])

    y = height - 112
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Assessment")
    y -= 15
    c.setFont("Helvetica", 8.6)
    for line in _wrap(assessment["summary"], 100):
        c.drawString(margin, y, line)
        y -= 11

    y -= 4
    c.setFillColor(colors.HexColor("#0b1f2a"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Top findings")
    y -= 13
    for finding in assessment["findings"][:6]:
        c.setFont("Helvetica-Bold", 8.4)
        c.setFillColor(colors.HexColor("#0b1f2a"))
        c.drawString(margin, y, f"{finding['rank']}. {finding['name']}  ·  {finding['severity']}  ·  {round(finding['confidence'] * 100)}%")
        c.setFont("Helvetica", 7.6)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(margin + 12, y - 9, f"{finding['changeExtentM2']:,} m² · €{finding['valueEur']:,} · {finding['access']} · {finding['review']}")
        y -= 22
        if y < 170:
            break

    _draw_minimap(c, scenario, margin, 64, width - 2 * margin, 92)
    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 6.8)
    c.drawString(margin, 52, f"Imagery: {scenario['meta']['imagery']['source']} · Model: {assessment['modelVersion']} · Simulated demo pack")
    c.drawString(margin, 43, assessment["disclosure"][:150])
    c.drawString(margin, 34, "© OpenStreetMap contributors (ODbL) · © Copernicus Sentinel data (demo pack is simulated)")
    c.showPage()
    c.save()
    return buffer.getvalue()


def _wrap(text: str, width: int) -> Iterable[str]:
    words = text.split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            yield line
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        yield line


def field_order_pdf(scenario: dict, assessment: dict, assignments: dict[str, str] | None = None) -> bytes:
    """One-page field order that matches the screen."""
    if not HAVE_REPORTLAB:  # pragma: no cover
        return b"{}"
    assignments = assignments or {}
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 42
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(colors.HexColor("#0b1f2a"))
    c.drawString(margin, height - 54, "FIELD ORDER")
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(margin, height - 68, f"{scenario['meta']['title']} · {scenario['meta']['eventDate']} · {scenario['meta']['areaKm2']:.0f} km²")
    y = height - 96
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0b1f2a"))
    c.drawString(margin, y, "Assignments")
    y -= 16
    by_team = {team: site for site, team in assignments.items()}
    for team in ("Team 1", "Team 2", "Team 3"):
        site_id = by_team.get(team)
        site = next((s for s in scenario["sites"] if s["id"] == site_id), None)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, y, team)
        c.setFont("Helvetica", 9)
        c.drawString(margin + 60, y, f"{site['name']} ({site['id']}) · {site['severity']} · {site['accessStatus']} access" if site else "Unassigned")
        y -= 20
    y -= 4
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, y, "Assessment")
    y -= 14
    c.setFont("Helvetica", 8.4)
    for line in _wrap(assessment["summary"], 105):
        c.drawString(margin, y, line)
        y -= 11
    _draw_minimap(c, scenario, margin, 60, width - 2 * margin, 100)
    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 7)
    c.drawString(margin, 48, f"AI-assisted. Analyst: {assessment['analyst']}. Model {assessment['modelVersion']}. Imagery: {scenario['meta']['imagery']['source']}.")
    c.drawString(margin, 39, "Human review required. Do not dispatch on model output alone.")
    c.showPage()
    c.save()
    return buffer.getvalue()


def qgis_project(scenario: dict, assessment: dict) -> str:
    """A minimal QGIS project referencing the exported GeoJSON layers."""
    bbox = scenario["meta"]["bbox"]
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" projectname="{scenario['meta']['id']}">
  <homePath path="."/>
  <title>{scenario['meta']['title']}</title>
  <extent>
    <xmin>{bbox[0]}</xmin><ymin>{bbox[1]}</ymin><xmax>{bbox[2]}</xmax><ymax>{bbox[3]}</ymax>
  </extent>
  <projectlayers>
    <maplayer type="vector" geometry="Point" name="GeoResponse findings">
      <datasource>findings.geojson</datasource>
      <provider>ogr</provider>
    </maplayer>
    <maplayer type="vector" geometry="Polygon" name="Change overlay">
      <datasource>change-overlay.geojson</datasource>
      <provider>ogr</provider>
    </maplayer>
  </projectlayers>
  <layer-tree-group name="GeoResponse">
    <layer-tree-layer name="Change overlay" source="change-overlay.geojson" providerKey="ogr"/>
    <layer-tree-layer name="GeoResponse findings" source="findings.geojson" providerKey="ogr"/>
  </layer-tree-group>
  <metadata>
    <property key="georesponse:model">{assessment['modelVersion']}</property>
    <property key="georesponse:provenance">{scenario['meta']['imagery']['source']}</property>
  </metadata>
</qgis>"""


def arcgis_export(scenario: dict, assessment: dict) -> bytes:
    features = findings_geojson(scenario, assessment)
    payload = {
        "name": f"georesponse-{scenario['meta']['id']}",
        "serviceType": "FeatureServer",
        "spatialReference": {"wkid": 4326},
        "fields": [
            {"name": "id", "type": "esriFieldTypeString"},
            {"name": "severity", "type": "esriFieldTypeString"},
            {"name": "confidence", "type": "esriFieldTypeDouble"},
            {"name": "valueEur", "type": "esriFieldTypeInteger"},
        ],
        "features": features,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("feature-service.json", json.dumps(payload, indent=2))
        archive.writestr("findings.geojson", json.dumps(features, indent=2))
        archive.writestr("README.txt", "ArcGIS Server import package. Publish as a feature layer (WGS84).\n")
    return buffer.getvalue()


def guidewire_claim_center(assessment: dict) -> dict:
    claim = assessment["claim"]
    return {
        "resource": "ClaimCenter",
        "endpoint": "/claim/v1/claims",
        "method": "POST",
        "body": {
            "claim": {
                "policyNumber": claim.get("claimRef"),
                "lossDate": claim.get("dateOfLoss"),
                "lossCause": claim.get("causeOfLoss"),
                "description": claim.get("damageSummary"),
                "insuredName": claim.get("insured"),
                "estimatedLoss": claim.get("reserveEstimateEur"),
                "adjusterRequired": True,
            },
            "attachments": claim["attachments"],
        },
        "note": "Map to the customer's Guidewire field names. Never auto-approves.",
    }


def duck_creek_claim(assessment: dict) -> dict:
    claim = assessment["claim"]
    return {
        "resource": "DuckCreek.Claims",
        "operation": "CreateClaim",
        "payload": {
            "PolicyNumber": claim.get("claimRef"),
            "LossDate": claim.get("dateOfLoss"),
            "Peril": claim.get("causeOfLoss"),
            "LossDescription": claim.get("damageSummary"),
            "ReserveAmount": claim.get("reserveEstimateEur"),
            "RequiresAdjuster": True,
        },
    }


def maximo_work_order(scenario: dict, site: dict) -> dict:
    return {
        "siteid": site["id"],
        "description": f"GeoResponse inspection — {site['name']}",
        "assetnum": (site.get("assets") or [{}])[0].get("id", "UNKNOWN"),
        "priority": {"red": 1, "orange": 2, "yellow": 3}[site["severity"]],
        "location": f"{site['lon']:.5f},{site['lat']:.5f}",
        "reportedby": "GeoResponse",
        "worktype": "INSPECTION",
        "targetstart": scenario["meta"]["eventDate"],
    }


def sap_maintenance_order(scenario: dict, site: dict) -> dict:
    return {
        "OrderType": "PM01",
        "Description": f"GeoResponse inspection {site['name']}",
        "Priority": {"red": "1", "orange": "2", "yellow": "3"}[site["severity"]],
        "FunctionalLocation": site.get("assetCode", site["id"]),
        "PlannedStart": scenario["meta"]["eventDate"],
        "LongText": f"AI-assisted finding. Value at risk €{site.get('valueEur', 0):,}. Human review required.",
    }


def dispatch_csv(scenario: dict, assignments: dict[str, str]) -> str:
    by_team = {team: site for site, team in assignments.items()}
    lines = ["team,site_id,site_name,lat,lon,severity,access,response_minutes"]
    for team in ("Team 1", "Team 2", "Team 3"):
        site = next((s for s in scenario["sites"] if s["id"] == by_team.get(team)), None)
        if not site:
            continue
        lines.append(
            f'{team},{site["id"]},"{site["name"]}",{site["lat"]:.5f},{site["lon"]:.5f},{site["severity"]},{site["accessStatus"]},'
            f'{site.get("responseMinutes", 18)}'
        )
    return "\n".join(lines)


def integrations_manifest() -> dict:
    return {
        "claims": ["Guidewire ClaimCenter", "Duck Creek Claims"],
        "gis": ["Esri ArcGIS Server", "QGIS"],
        "field": ["IBM Maximo", "SAP PM", "CSV dispatch"],
        "imagery": ["Sentinel-2 (STAC)", "Sentinel-1 SAR", "Planet", "Maxar", "Airbus", "ICEYE", "Capella", "drone orthophoto"],
        "note": "Adapters are pure transforms; production adds credentials and queueing.",
        "policies": {"autoApprove": False, "humanInTheLoop": True, "template": PILOT.template},
    }
