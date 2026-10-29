"""Optional FastAPI surface for pilot deployments.

The stage app is static and does not need this service.  The API exists for the
pilot integration path: review decisions, exports and the audit chain.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import MODEL_VERSION
from .assessment import write_assessment
from .audit import append_event, read_events, verify_chain
from .config import DATA_DIR, ROOT
from .exports import (
    arcgis_export,
    assessment_pdf,
    dispatch_csv,
    duck_creek_claim,
    export_geojson_bundle,
    field_order_pdf,
    guidewire_claim_center,
    integrations_manifest,
    maximo_work_order,
    qgis_project,
    sap_maintenance_order,
)
from .ranking import rank_sites
from .security import privacy_review
from .proactive.api import router as proactive_router

app = FastAPI(title="GeoResponse API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
AUDIT_PATH = ROOT / "runtime" / "audit.jsonl"


class ReviewRequest(BaseModel):
    reviews: dict[str, str] = Field(default_factory=dict)
    teams: int = 3
    analyst: str = "A. Weber"


class AuditRequest(BaseModel):
    action: str
    siteId: str | None = None
    analyst: str | None = None
    detail: dict = Field(default_factory=dict)
    imagery: str | None = None
    modelVersion: str = MODEL_VERSION


def _scenario(scenario_id: str) -> dict:
    path = Path(DATA_DIR) / "scenarios" / f"{scenario_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario_id}")
    return json.loads(path.read_text(encoding="utf-8"))


app.include_router(proactive_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_VERSION, "scenarios": len(list((Path(DATA_DIR) / "scenarios").glob("*.json")))}


@app.get("/api/scenarios")
def scenarios() -> dict:
    return json.loads((Path(DATA_DIR) / "index.json").read_text(encoding="utf-8"))


@app.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id: str) -> dict:
    return _scenario(scenario_id)


@app.post("/api/scenarios/{scenario_id}/assessment")
def assess(scenario_id: str, request: ReviewRequest) -> dict:
    data = _scenario(scenario_id)
    excluded = {sid for sid, status in request.reviews.items() if status == "rejected"}
    ranked, warnings = rank_sites(data["sites"], exclude=excluded)
    assessment = write_assessment(data, ranked, reviews=request.reviews, teams=request.teams, analyst=request.analyst)
    assessment["warnings"] = warnings
    assessment["modelVersion"] = MODEL_VERSION
    return assessment


@app.get("/api/scenarios/{scenario_id}/exports/geojson")
def geojson_export(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    return Response(
        export_geojson_bundle(data, data["assessmentAfterReview"]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="georesponse-{scenario_id}.zip"'},
    )


@app.get("/api/scenarios/{scenario_id}/assessment.pdf")
def pdf_export(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    return Response(
        assessment_pdf(data, data["assessmentAfterReview"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="georesponse-{scenario_id}.pdf"'},
    )


@app.get("/api/scenarios/{scenario_id}/field-order.pdf")
def field_order_export(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    assignments = {a["siteId"]: a["team"] for a in data["fieldOrder"]["assignments"]}
    return Response(
        field_order_pdf(data, data["assessmentAfterReview"], assignments),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="field-order-{scenario_id}.pdf"'},
    )


@app.get("/api/scenarios/{scenario_id}/qgis")
def qgis_export(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    return Response(
        qgis_project(data, data["assessmentAfterReview"]),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="georesponse-{scenario_id}.qgs"'},
    )


@app.get("/api/scenarios/{scenario_id}/arcgis")
def arcgis(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    return Response(
        arcgis_export(data, data["assessmentAfterReview"]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="arcgis-{scenario_id}.zip"'},
    )


@app.get("/api/scenarios/{scenario_id}/dispatch.csv")
def dispatch(scenario_id: str) -> Response:
    data = _scenario(scenario_id)
    assignments = {a["siteId"]: a["team"] for a in data["fieldOrder"]["assignments"]}
    return Response(dispatch_csv(data, assignments), media_type="text/csv")


@app.get("/api/scenarios/{scenario_id}/claims/guidewire")
def guidewire(scenario_id: str) -> dict:
    return guidewire_claim_center(_scenario(scenario_id)["assessmentAfterReview"])


@app.get("/api/scenarios/{scenario_id}/claims/duckcreek")
def duckcreek(scenario_id: str) -> dict:
    return duck_creek_claim(_scenario(scenario_id)["assessmentAfterReview"])


@app.get("/api/scenarios/{scenario_id}/work/{system}/{site_id}")
def work_order(scenario_id: str, system: str, site_id: str) -> dict:
    data = _scenario(scenario_id)
    site = next((s for s in data["sites"] if s["id"] == site_id), None)
    if site is None:
        raise HTTPException(status_code=404, detail="unknown site")
    if system == "maximo":
        return maximo_work_order(data, site)
    if system == "sap":
        return sap_maintenance_order(data, site)
    raise HTTPException(status_code=404, detail="unknown system")


@app.get("/api/dashboard")
def dashboard() -> dict:
    return json.loads((Path(DATA_DIR) / "pilot.json").read_text(encoding="utf-8"))


@app.get("/api/monitoring")
def monitoring() -> dict:
    return json.loads((Path(DATA_DIR) / "monitoring.json").read_text(encoding="utf-8"))


@app.get("/api/integrations")
def integrations() -> dict:
    return integrations_manifest()


@app.get("/api/privacy")
def privacy() -> dict:
    return privacy_review({"lawful_basis", "minimisation", "access", "human_review"})


@app.post("/api/audit")
def audit(request: AuditRequest) -> dict:
    return append_event(
        AUDIT_PATH,
        {
            "action": request.action,
            "siteId": request.siteId,
            "analyst": request.analyst,
            "detail": request.detail,
            "imagery": request.imagery,
            "modelVersion": request.modelVersion,
        },
    )


@app.get("/api/audit")
def audit_list() -> dict:
    events = read_events(AUDIT_PATH)
    ok, message = verify_chain(events)
    return {"events": events, "verified": ok, "message": message}


# Serve the built SPA when it is present (Docker / private host).  API routes are
# registered above, so /api keeps priority over the static mount.
_dist = Path(ROOT) / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="web")
