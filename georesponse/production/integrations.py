"""Live system integrations.

The payload builders stay in `proactive.integrations`; this module performs the
real HTTP calls when credentials are configured.  Unconfigured targets raise.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from ..proactive import integrations as payloads
from ..proactive.models import Alert
from .config import IntegrationSettings, get_settings


class IntegrationUnavailable(RuntimeError):
    pass


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    return (client, False) if client else (httpx.Client(timeout=30), True)


def _post(url: str, payload: dict, *, headers: dict, client: httpx.Client | None = None) -> dict:
    http, owned = _client(client)
    try:
        response = http.post(url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            body = response.json()
        except Exception:
            body = response.text[:800]
        return {"ok": True, "status": response.status_code, "body": body}
    finally:
        if owned:
            http.close()


def create_jira(alert: Alert, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    if not (settings.jira_url and settings.jira_token):
        raise IntegrationUnavailable("Jira is not configured")
    payload = payloads.create_jira_issue(alert)["issue"]
    payload["fields"]["project"] = {"key": settings.jira_project}
    auth = base64.b64encode(f"{settings.jira_email}:{settings.jira_token}".encode()).decode()
    return _post(settings.jira_url.rstrip("/") + "/rest/api/3/issue", payload, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}, client=client)


def create_service_now(alert: Alert, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    if not (settings.servicenow_url and settings.servicenow_user):
        raise IntegrationUnavailable("ServiceNow is not configured")
    payload = payloads.create_service_now_incident(alert)["incident"]
    auth = base64.b64encode(f"{settings.servicenow_user}:{settings.servicenow_password}".encode()).decode()
    return _post(settings.servicenow_url.rstrip("/") + "/api/now/table/incident", payload, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}, client=client)


def create_claim(alert: Alert, system: str, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    url = settings.guidewire_url if system == "guidewire" else settings.duckcreek_url
    token = settings.guidewire_token if system == "guidewire" else settings.duckcreek_token
    if not (url and token):
        raise IntegrationUnavailable(f"{system} is not configured")
    payload = payloads.create_claim_draft(alert, system)
    return _post(url, payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, client=client)


def create_inspection(alert: Alert, system: str, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    url = settings.maximo_url if system == "maximo" else settings.sap_url
    if not url:
        raise IntegrationUnavailable(f"{system} is not configured")
    payload = payloads.create_inspection_request(alert, system)
    if system == "maximo":
        headers = {"Authorization": f"Bearer {settings.maximo_token}", "Content-Type": "application/json"}
    else:
        auth = base64.b64encode(f"{settings.sap_user}:{settings.sap_password}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    return _post(url, payload, headers=headers, client=client)


def push_arcgis(alert: Alert, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    if not (settings.arcgis_url and settings.arcgis_token):
        raise IntegrationUnavailable("ArcGIS is not configured")
    layer = payloads.arcgis_feature_layer(alert.tenant, [alert], [])
    payload = {"features": [f for f in layer["features"]], "f": "json", "token": settings.arcgis_token}
    return _post(settings.arcgis_url, payload, headers={"Content-Type": "application/json"}, client=client)


def push_siem(alert: Alert, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().integrations
    if not (settings.siem_url and settings.siem_token):
        raise IntegrationUnavailable("SIEM is not configured")
    event = payloads.siem_event(alert)
    payload = {"event": event, "sourcetype": "georesponse:alert"}
    return _post(settings.siem_url, payload, headers={"Authorization": f"Splunk {settings.siem_token}", "Content-Type": "application/json"}, client=client)


def dispatch(target: str, alert: Alert, *, settings: IntegrationSettings | None = None, client: httpx.Client | None = None) -> dict:
    if target == "jira":
        return create_jira(alert, settings=settings, client=client)
    if target in {"servicenow", "service-now"}:
        return create_service_now(alert, settings=settings, client=client)
    if target in {"guidewire", "duckcreek"}:
        return create_claim(alert, target, settings=settings, client=client)
    if target in {"maximo", "sap"}:
        return create_inspection(alert, target, settings=settings, client=client)
    if target == "arcgis":
        return push_arcgis(alert, settings=settings, client=client)
    if target == "siem":
        return push_siem(alert, settings=settings, client=client)
    raise IntegrationUnavailable(f"unknown live target: {target}")


def status(settings: IntegrationSettings | None = None) -> dict:
    settings = settings or get_settings().integrations
    return settings.safe()
