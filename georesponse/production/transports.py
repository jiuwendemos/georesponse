"""Real notification transports.

Every transport raises when its credentials are missing; the outbox turns that
into a failed/dead notification rather than a fake success.
"""

from __future__ import annotations

import base64
import json
import smtplib
from email.message import EmailMessage
from typing import Callable

import httpx

from ..proactive.models import Notification
from .config import ChannelSettings, get_settings


class TransportError(RuntimeError):
    pass


def _post(url: str, payload: dict, *, headers: dict | None = None, timeout: float = 20, client: httpx.Client | None = None) -> dict:
    owned = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.post(url, json=payload, headers=headers or {})
        response.raise_for_status()
        try:
            body = response.json()
        except Exception:
            body = response.text[:500]
        return {"status": response.status_code, "body": body}
    finally:
        if owned:
            client.close()


def send_email(notification: Notification, *, settings: ChannelSettings | None = None) -> dict:
    settings = settings or get_settings().channels
    if not settings.smtp_host:
        raise TransportError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = notification.recipient
    message["Subject"] = notification.subject
    message.set_content(notification.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    return {"channel": "email", "to": notification.recipient}


def send_slack(notification: Notification, *, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().channels
    if not settings.slack_webhook:
        raise TransportError("Slack webhook is not configured")
    return _post(settings.slack_webhook, notification.payload, client=client)


def send_teams(notification: Notification, *, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().channels
    if not settings.teams_webhook:
        raise TransportError("Teams webhook is not configured")
    card = notification.payload
    adaptive = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
    return _post(settings.teams_webhook, adaptive, client=client)


def send_sms(notification: Notification, *, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().channels
    if not (settings.twilio_account_sid and settings.twilio_token and settings.twilio_from):
        raise TransportError("Twilio is not configured")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    auth = base64.b64encode(f"{settings.twilio_account_sid}:{settings.twilio_token}".encode()).decode()
    data = {"From": settings.twilio_from, "To": notification.recipient, "Body": notification.payload.get("text", notification.body)}
    owned = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.post(url, data=data, headers={"Authorization": f"Basic {auth}"})
        response.raise_for_status()
        return {"status": response.status_code}
    finally:
        if owned:
            client.close()


def send_pager(notification: Notification, *, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().channels
    if not settings.pagerduty_routing_key:
        raise TransportError("PagerDuty routing key is not configured")
    payload = {
        "routing_key": settings.pagerduty_routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": notification.subject,
            "source": "georesponse",
            "severity": "critical",
            "custom_details": {"alertId": notification.alert_id, "link": notification.payload.get("deepLink")},
        },
    }
    return _post("https://events.pagerduty.com/v2/enqueue", payload, client=client)


def send_webhook(notification: Notification, *, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings().channels
    if not settings.generic_webhook:
        raise TransportError("Generic webhook is not configured")
    headers = {"Content-Type": "application/json"}
    if notification.signature:
        headers["X-GeoResponse-Signature"] = notification.signature
    return _post(settings.generic_webhook, notification.payload, headers=headers, client=client)


def build_transport_map(*, settings: ChannelSettings | None = None, client: httpx.Client | None = None) -> dict[str, Callable[[Notification], dict]]:
    settings = settings or get_settings().channels
    return {
        "email": lambda notification: send_email(notification, settings=settings),
        "slack": lambda notification: send_slack(notification, settings=settings, client=client),
        "teams": lambda notification: send_teams(notification, settings=settings, client=client),
        "sms": lambda notification: send_sms(notification, settings=settings, client=client),
        "pager": lambda notification: send_pager(notification, settings=settings, client=client),
        "webhook": lambda notification: send_webhook(notification, settings=settings, client=client),
    }


def channel_status(settings: ChannelSettings | None = None) -> dict:
    settings = settings or get_settings().channels
    return {
        "email": bool(settings.smtp_host),
        "slack": bool(settings.slack_webhook),
        "teams": bool(settings.teams_webhook),
        "sms": bool(settings.twilio_account_sid and settings.twilio_token and settings.twilio_from),
        "pager": bool(settings.pagerduty_routing_key),
        "webhook": bool(settings.generic_webhook),
    }
