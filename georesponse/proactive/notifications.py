"""Notification outbox, channels, quiet hours and delivery retries.

No network is used in the demo.  Each provider builds the real payload and can be
swapped for a live transport without changing the alert lifecycle.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from .models import Alert, Notification, TenantPreferences, add_hours, new_id, now_iso, parse_iso, utcnow
from .store import ProactiveStore

MAX_ATTEMPTS = 3


def sign_payload(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def signed_deep_link(base: str, alert_id: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), alert_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"{base}#watch/alert/{alert_id}?sig={signature}"


def quiet_now(prefs: TenantPreferences, moment: datetime) -> bool:
    if not prefs.quiet_hours:
        return False
    start, end = prefs.quiet_hours
    hour = moment.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def should_send(alert: Alert, prefs: TenantPreferences, moment: datetime | None = None) -> tuple[bool, str]:
    moment = moment or utcnow()
    if prefs.paused or prefs.kill_switch:
        return False, "tenant monitoring paused"
    if quiet_now(prefs, moment) and alert.severity != "red":
        return False, "quiet hours"
    return True, "ok"


def render_email(alert: Alert, link: str, language: str = "en") -> tuple[str, str]:
    if language.startswith("de"):
        subject = f"[GeoResponse] {alert.severity.upper()} · {alert.title}"
        body = (
            f"Neue Beobachtung in {alert.scope_id}.\n\n"
            f"{alert.summary}\n\n"
            f"Konfidenz: {round(alert.confidence * 100)}%\n"
            f"Status: {alert.status}\n"
            f"Prüfen: {link}\n\n"
            "Menschliche Prüfung erforderlich. Keine automatische Entscheidung."
        )
        return subject, body
    subject = f"[GeoResponse] {alert.severity.upper()} · {alert.title}"
    body = (
        f"New change detected in {alert.scope_id}.\n\n"
        f"{alert.summary}\n\n"
        f"Confidence: {round(alert.confidence * 100)}%\n"
        f"Status: {alert.status}\n"
        f"Review: {link}\n\n"
        "Human review required. GeoResponse never approves a claim or dispatches a crew automatically."
    )
    return subject, body


def slack_blocks(alert: Alert, link: str) -> dict:
    return {
        "text": f"{alert.severity.upper()} · {alert.title}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"{alert.severity.upper()} · {alert.title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": alert.summary}},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Scope `{alert.scope_id}` · confidence *{round(alert.confidence*100)}%* · `{alert.status}`"}
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Open alert"}, "url": link, "style": "primary"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Acknowledge"}, "value": alert.id, "action_id": "acknowledge_alert"},
                ],
            },
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Human review required · no automatic dispatch"}]},
        ],
    }


def teams_card(alert: Alert, link: str) -> dict:
    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": f"{alert.severity.upper()} · {alert.title}"},
            {"type": "TextBlock", "text": alert.summary, "wrap": True},
            {"type": "FactSet", "facts": [
                {"title": "Scope", "value": alert.scope_id},
                {"title": "Confidence", "value": f"{round(alert.confidence * 100)}%"},
                {"title": "Status", "value": alert.status},
            ]},
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "Open alert", "url": link},
            {"type": "Action.Submit", "title": "Acknowledge", "data": {"action": "acknowledge", "alertId": alert.id}},
        ],
        "msteams": {"width": "Full"},
    }


def sms_text(alert: Alert, link: str) -> str:
    return f"GeoResponse {alert.severity.upper()}: {alert.title}. {round(alert.confidence*100)}% confidence. Review: {link}"


def webhook_payload(alert: Alert, link: str, secret: str) -> dict:
    body = {
        "event": "alert.created",
        "alert": {
            "id": alert.id,
            "scopeId": alert.scope_id,
            "severity": alert.severity,
            "confidence": alert.confidence,
            "title": alert.title,
            "summary": alert.summary,
            "status": alert.status,
            "deepLink": link,
        },
        "humanReviewRequired": True,
    }
    return {**body, "signature": sign_payload(body, secret)}


class DryRunProvider:
    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[dict] = []

    def send(self, notification: Notification) -> dict:
        record = {"channel": self.channel, "to": notification.recipient, "subject": notification.subject, "id": notification.id}
        self.sent.append(record)
        return {"ok": True, "provider": f"dry-run-{self.channel}", "detail": record}


class NotificationService:
    def __init__(self, store: ProactiveStore, *, secret: str = "demo-webhook-secret", base_url: str = "https://georesponse.example/", live: bool = False) -> None:
        self.store = store
        self.secret = secret
        self.base_url = base_url
        self.live = live
        if live:
            from ..production.transports import build_transport_map

            self.providers = build_transport_map()
        else:
            self.providers: dict[str, Callable[[Notification], dict]] = {
                channel: DryRunProvider(channel).send for channel in ("email", "slack", "teams", "sms", "pager", "webhook")
            }

    def enqueue(self, alert: Alert, prefs: TenantPreferences | None = None, *, moment: datetime | None = None) -> list[Notification]:
        prefs = prefs or self.store.get_preferences(alert.tenant)
        allowed, reason = should_send(alert, prefs, moment)
        if not allowed:
            self.store.audit(alert.tenant, "notification.suppressed", alert_id=alert.id, detail={"reason": reason})
            return []
        link = signed_deep_link(self.base_url, alert.id, self.secret)
        subject, body = render_email(alert, link, prefs.language)
        recipients = prefs.recipients or [{"email": "ops@example.com", "name": "Ops", "channels": prefs.channels}]
        created: list[Notification] = []
        for recipient in recipients:
            channels = recipient.get("channels") or prefs.channels
            for channel in channels:
                payload = {
                    "email": {"subject": subject, "body": body},
                    "slack": slack_blocks(alert, link),
                    "teams": teams_card(alert, link),
                    "sms": {"text": sms_text(alert, link)},
                    "pager": {"text": sms_text(alert, link)},
                    "webhook": webhook_payload(alert, link, self.secret),
                }[channel]
                signature = sign_payload(payload, self.secret) if channel in {"webhook", "slack", "teams"} else None
                notification = Notification(
                    id=new_id("NOT"),
                    tenant=alert.tenant,
                    alert_id=alert.id,
                    channel=channel,
                    recipient=recipient.get("email") or recipient.get("name") or "ops",
                    subject=subject,
                    body=body,
                    payload=payload,
                    signature=signature,
                )
                self.store.save_notification(notification)
                created.append(notification)
        self.store.audit(alert.tenant, "notification.queued", alert_id=alert.id, detail={"count": len(created)})
        return created

    def deliver_due(self, moment: datetime | None = None, limit: int = 100) -> dict:
        moment = moment or utcnow()
        sent, failed, dead = [], [], []
        for notification in self.store.due_notifications(moment, limit):
            provider = self.providers.get(notification.channel)
            if not provider:
                notification.status = "dead"
                notification.error = f"unknown channel {notification.channel}"
                self.store.save_notification(notification)
                dead.append(notification.id)
                continue
            try:
                result = provider(notification)
                notification.status = "sent"
                notification.sent_at = now_iso(moment)
                notification.error = None
                notification.payload = {**notification.payload, "providerResult": result}
                self.store.save_notification(notification)
                sent.append(notification.id)
            except Exception as exc:  # noqa: BLE001
                notification.attempts += 1
                notification.error = str(exc)
                if notification.attempts >= MAX_ATTEMPTS:
                    notification.status = "dead"
                    dead.append(notification.id)
                else:
                    notification.status = "failed"
                    notification.next_attempt_at = add_hours(moment, 2**notification.attempts)
                    failed.append(notification.id)
                self.store.save_notification(notification)
        return {"sent": sent, "failed": failed, "dead": dead}

    def outbox(self, tenant: str | None = None) -> list[dict]:
        return [
            {
                "id": item.id,
                "alertId": item.alert_id,
                "channel": item.channel,
                "recipient": item.recipient,
                "status": item.status,
                "attempts": item.attempts,
                "nextAttemptAt": item.next_attempt_at,
                "error": item.error,
            }
            for item in self.store.list_notifications(tenant=tenant)
        ]

    def retry_dead(self, notification_id: str, moment: datetime | None = None) -> Notification:
        notification = next((n for n in self.store.list_notifications(limit=1000) if n.id == notification_id), None)
        if notification is None:
            raise KeyError(notification_id)
        notification.status = "queued"
        notification.attempts = 0
        notification.next_attempt_at = now_iso(moment or utcnow())
        self.store.save_notification(notification)
        return notification


def filter_recipients(recipients: list[dict], *, allowed_roles: set[str] | None = None, allowed_channels: set[str] | None = None) -> list[dict]:
    """Least-privilege delivery: only recipients and channels explicitly allowed."""
    result = []
    for recipient in recipients:
        role = recipient.get("role")
        if allowed_roles and role and role not in allowed_roles:
            continue
        channels = recipient.get("channels", [])
        if allowed_channels:
            channels = [channel for channel in channels if channel in allowed_channels]
        if channels:
            result.append({**recipient, "channels": channels})
    return result


def preferences_payload(prefs: TenantPreferences) -> dict:
    return {
        "channels": prefs.channels,
        "quietHours": prefs.quiet_hours,
        "digest": prefs.digest,
        "language": prefs.language,
        "alertBudgetPerDay": prefs.alert_budget_per_day,
        "escalationMinutes": prefs.escalation_minutes,
        "paused": prefs.paused,
        "killSwitch": prefs.kill_switch,
        "recipients": prefs.recipients,
    }
