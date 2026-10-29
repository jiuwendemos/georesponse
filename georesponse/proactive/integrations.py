"""Proactive handoff adapters: ticketing, claims, CMMS, GIS, dispatch, SIEM.

They are pure payload builders.  A live deployment swaps the transport; the demo
records the payload and never sends it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .alerts import handoff_payload
from .models import Alert, Incident, Scope, now_iso


def create_jira_issue(alert: Alert) -> dict:
    return {
        "system": "jira",
        "dryRun": True,
        "requiresHuman": True,
        "issue": {
            "fields": {
                "project": {"key": "GEO"},
                "issuetype": {"name": "Task"},
                "summary": f"[GeoResponse] {alert.title}",
                "description": f"{alert.summary}\n\nAlert: {alert.id}\nScope: {alert.scope_id}\nConfidence: {round(alert.confidence*100)}%",
                "priority": {"name": "Highest" if alert.severity == "red" else "High" if alert.severity == "orange" else "Medium"},
                "labels": ["georesponse", alert.change_type, alert.scope_id],
            }
        },
    }


def create_service_now_incident(alert: Alert) -> dict:
    return {
        "system": "servicenow",
        "dryRun": True,
        "requiresHuman": True,
        "incident": {
            "short_description": f"GeoResponse: {alert.title}",
            "description": alert.summary,
            "urgency": "1" if alert.severity == "red" else "2",
            "impact": "1" if alert.value_eur > 5_000_000 else "2",
            "category": "geospatial monitoring",
            "correlation_id": alert.id,
            "caller_id": "georesponse",
        },
    }


def create_claim_draft(alert: Alert, system: str = "guidewire") -> dict:
    payload = handoff_payload(alert, "claim")
    return {
        **payload,
        "system": system,
        "draft": {
            "policyHint": alert.asset or alert.scope_id,
            "lossDate": alert.created_at[:10],
            "causeOfLoss": alert.change_type,
            "estimatedLossEur": round(alert.value_eur * 0.05),
            "adjusterRequired": True,
            "attachments": [alert.evidence.get("after")] if alert.evidence else [],
        },
        "dryRun": True,
    }


def create_inspection_request(alert: Alert, system: str = "maximo") -> dict:
    return {
        **handoff_payload(alert, "inspection"),
        "system": system,
        "workOrder": {
            "description": f"GeoResponse inspection — {alert.title}",
            "asset": alert.asset or alert.scope_id,
            "priority": 1 if alert.severity == "red" else 2,
            "location": f"{alert.lon:.5f},{alert.lat:.5f}",
            "workType": "INSPECTION",
            "reportedBy": "GeoResponse",
            "humanApprovalRequired": True,
        },
        "dryRun": True,
    }


def arcgis_feature_layer(tenant: str, alerts: list[Alert], scopes: list[Scope]) -> dict:
    features = []
    for alert in alerts:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [alert.lon, alert.lat]},
                "properties": {
                    "alertId": alert.id,
                    "scopeId": alert.scope_id,
                    "severity": alert.severity,
                    "status": alert.status,
                    "confidence": alert.confidence,
                },
            }
        )
    return {
        "name": f"georesponse-{tenant}-alerts",
        "serviceType": "FeatureServer",
        "spatialReference": {"wkid": 4326},
        "features": features,
        "scopes": [{"id": s.id, "name": s.name, "bbox": s.bbox} for s in scopes],
        "dryRun": True,
    }


def qgis_monitoring_project(tenant: str, scopes: list[Scope], alerts: list[Alert]) -> str:
    layers = "\n".join(
        f'    <layer-tree-layer name="{scope.name}" source="scope-{scope.id}.geojson" providerKey="ogr"/>'
        for scope in scopes
    )
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" projectname="georesponse-{tenant}-watch">
  <title>GeoResponse proactive watch — {tenant}</title>
  <layer-tree-group name="GeoResponse watch">
{layers}
  </layer-tree-group>
  <metadata>
    <property key="georesponse:alerts">{len(alerts)}</property>
    <property key="georesponse:mode">proactive</property>
  </metadata>
</qgis>"""


def field_dispatch(alert: Alert, team: str = "Team 1") -> dict:
    return {
        "system": "dispatch",
        "dryRun": True,
        "requiresHuman": True,
        "assignment": {
            "team": team,
            "alertId": alert.id,
            "scopeId": alert.scope_id,
            "location": [alert.lon, alert.lat],
            "severity": alert.severity,
            "access": alert.access,
            "note": "Draft only. A human commits the team.",
        },
    }


def siem_event(alert: Alert) -> dict:
    return {
        "source": "georesponse",
        "eventType": "georesponse.alert",
        "severity": alert.severity,
        "timestamp": now_iso(),
        "alertId": alert.id,
        "tenant": alert.tenant,
        "scopeId": alert.scope_id,
        "summary": alert.summary,
        "modelVersion": alert.model_version,
        "humanReviewRequired": True,
    }


def sync_status(alert: Alert, system: str, external_id: str, status: str) -> dict:
    return {
        "alertId": alert.id,
        "system": system,
        "externalId": external_id,
        "status": status,
        "syncedAt": now_iso(),
        "direction": "outbound",
        "humanReviewRequired": True,
    }


def dispatch_system(target: str, alert: Alert) -> dict:
    table = {
        "jira": create_jira_issue,
        "servicenow": create_service_now_incident,
        "guidewire": lambda a: create_claim_draft(a, "guidewire"),
        "duckcreek": lambda a: create_claim_draft(a, "duckcreek"),
        "maximo": lambda a: create_inspection_request(a, "maximo"),
        "sap": lambda a: create_inspection_request(a, "sap"),
        "dispatch": field_dispatch,
        "siem": siem_event,
    }
    if target not in table:
        raise ValueError(f"unknown integration: {target}")
    payload = table[target](alert)
    return {"status": "queued", "dryRun": True, "requiresHuman": True, "payload": payload}


def integration_manifest() -> dict:
    return {
        "notifications": ["email", "slack", "teams", "sms", "pager", "webhook"],
        "ticketing": ["jira", "servicenow"],
        "claims": ["guidewire", "duckcreek"],
        "cmms": ["maximo", "sap"],
        "gis": ["arcgis", "qgis"],
        "field": ["dispatch"],
        "security": ["siem"],
        "default": {"dryRun": True, "requiresHuman": True, "autoDispatch": False},
    }
