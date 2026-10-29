"""Proactive monitoring domain model.

Plain dataclasses with explicit JSON round-trips keep the API, SQLite store,
scheduler and UI on one vocabulary.  Time is always UTC ISO-8601.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

ALERT_SCHEMA_VERSION = "alert.v1"
DISMISS_REASONS = {
    "false_positive": "Model or baseline false positive",
    "known_event": "Already known to the customer",
    "cloud_shadow": "Cloud, shadow or season artefact",
    "no_action": "Real change, no action warranted",
    "duplicate": "Duplicate of another alert",
    "access": "Site not accessible or out of scope",
    "other": "Other — requires a note",
}
ALERT_STATES = ("new", "acknowledged", "assigned", "investigating", "resolved", "dismissed")
INCIDENT_STATES = ("open", "investigating", "resolved", "dismissed")
SCOPE_KINDS = ("corridor", "portfolio", "aoi", "asset")
CADENCES = ("6h", "12h", "daily", "weekly", "event")
SUBSCRIPTION_TIERS = ("weekly", "daily", "surge", "24-7")
CHANNELS = ("email", "slack", "teams", "sms", "pager", "webhook")
CHANGE_TYPES = ("flood", "wildfire", "construction", "vegetation", "erosion", "structure", "sar-change")
NON_GOALS = (
    "automated-claim-approval",
    "automatic-dispatch",
    "person-surveillance",
    "live-video",
    "individual-behaviour",
    "unscoped-monitoring",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso(moment: datetime | None = None) -> str:
    return (moment or utcnow()).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hours_since(value: str | None, moment: datetime | None = None) -> float:
    start = parse_iso(value)
    if not start:
        return 10**9
    return ((moment or utcnow()) - start).total_seconds() / 3600


def hours_between(start: str, end: str) -> float:
    a, b = parse_iso(start), parse_iso(end)
    if not a or not b:
        return 0.0
    return (b - a).total_seconds() / 3600


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Scope:
    id: str
    tenant: str
    name: str
    kind: str
    region: str
    center: tuple[float, float]
    bbox: tuple[float, float, float, float]
    asset_class: str
    change_types: list[str]
    cadence: str = "weekly"
    priority: int = 3
    subscription_tier: str = "weekly"
    status: str = "active"
    freshness_slo_hours: float = 168
    exclusions: list[tuple[float, float, float, float]] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise ValueError(f"unknown scope kind: {self.kind}")
        if self.cadence not in CADENCES:
            raise ValueError(f"unknown cadence: {self.cadence}")
        if self.subscription_tier not in SUBSCRIPTION_TIERS:
            raise ValueError(f"unknown subscription tier: {self.subscription_tier}")
        self.center = tuple(self.center)  # type: ignore[assignment]
        self.bbox = tuple(self.bbox)  # type: ignore[assignment]

    @property
    def area_km2(self) -> float:
        west, south, east, north = self.bbox
        lat = (south + north) / 2
        return abs(east - west) * 111.32 * abs(north - south) * 111.32 * 0.7

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Scope":
        return cls(**payload)


@dataclass
class MonitoringPlan:
    scope_id: str
    cadence: str = "weekly"
    sources: list[str] = field(default_factory=lambda: ["sentinel-2", "sentinel-1"])
    cloud_policy: str = "optical-under-30-else-sar"
    threshold_sigma: float = 2.5
    min_change: float = 0.06
    recipients: list[str] = field(default_factory=list)
    sla_hours: float = 4
    quiet_hours: tuple[int, int] | None = (22, 7)
    digest: str = "instant"
    escalation: list[dict] = field(default_factory=list)
    budget_eur_per_month: float = 2500
    paused: bool = False
    kill_switch: bool = False
    coverage_mode: str = "best-effort"
    retention_days: int = 365
    first_n_alerts_require_analyst: int = 3
    language: str = "en"
    channels: list[str] = field(default_factory=lambda: ["email", "slack"])
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if self.cadence not in CADENCES:
            raise ValueError(f"unknown cadence: {self.cadence}")
        if self.digest not in {"instant", "daily", "weekly"}:
            raise ValueError(f"unknown digest: {self.digest}")
        if self.quiet_hours is not None:
            self.quiet_hours = tuple(self.quiet_hours)  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "MonitoringPlan":
        return cls(**payload)


@dataclass
class Acquisition:
    id: str
    scope_id: str
    source: str
    scheduled_for: str
    status: str = "planned"  # planned, ordered, received, rejected, failed
    cloud_forecast: float = 0.2
    cost_eur: float = 0.0
    priority: int = 3
    attempts: int = 0
    next_attempt_at: str | None = None
    idempotency_key: str = ""
    bbox: tuple[float, float, float, float] | None = None
    resolution_m: float = 10.0
    scene_id: str | None = None
    received_at: str | None = None
    readiness: float = 0.0
    blind_spot_reason: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Acquisition":
        return cls(**payload)


@dataclass
class Baseline:
    scope_id: str
    metric: str
    values: list[float] = field(default_factory=list)
    season: str = "annual"
    mean: float = 0.0
    std: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    trend: str = "stable"
    updated_at: str = field(default_factory=now_iso)
    model_version: str = ""
    confirmed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def recompute(self) -> "Baseline":
        import statistics

        if self.values:
            self.mean = round(statistics.mean(self.values), 6)
            self.std = round(statistics.pstdev(self.values), 6)
            self.minimum = round(min(self.values), 6)
            self.maximum = round(max(self.values), 6)
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Baseline":
        return cls(**payload)


@dataclass
class Alert:
    id: str
    tenant: str
    scope_id: str
    title: str
    summary: str
    severity: str
    urgency: float
    confidence: float
    change_type: str
    observed: float
    baseline: float
    lon: float
    lat: float
    incident_id: str | None = None
    status: str = "new"
    assignee: str | None = None
    sla_due: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    dismissed_reason: str | None = None
    dismissal_note: str | None = None
    asset: str | None = None
    value_eur: int = 0
    population: int = 0
    access: str = "clear"
    source: str = "sentinel-2"
    model_version: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    why: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str = ""
    schema_version: str = ALERT_SCHEMA_VERSION
    validated_by: str | None = None
    validation_count: int = 0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in ALERT_STATES:
            raise ValueError(f"unknown alert state: {self.status}")
        if self.change_type not in CHANGE_TYPES:
            raise ValueError(f"unknown change type: {self.change_type}")
        if not self.dedupe_key:
            self.dedupe_key = f"{self.scope_id}:{self.change_type}:{round(self.lon, 3)}:{round(self.lat, 3)}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Alert":
        payload.setdefault("dedupe_key", "")
        return cls(**payload)


@dataclass
class Incident:
    id: str
    tenant: str
    scope_id: str
    title: str
    severity: str
    status: str = "open"
    alert_ids: list[str] = field(default_factory=list)
    assignee: str | None = None
    opened_at: str = field(default_factory=now_iso)
    closed_at: str | None = None
    summary: str = ""
    timeline: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in INCIDENT_STATES:
            raise ValueError(f"unknown incident state: {self.status}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Incident":
        return cls(**payload)


@dataclass
class Notification:
    id: str
    tenant: str
    alert_id: str
    channel: str
    recipient: str
    subject: str
    body: str
    status: str = "queued"  # queued, sent, failed, dead
    attempts: int = 0
    next_attempt_at: str | None = None
    created_at: str = field(default_factory=now_iso)
    sent_at: str | None = None
    error: str | None = None
    signature: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ValueError(f"unknown channel: {self.channel}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Notification":
        return cls(**payload)


@dataclass
class Forecast:
    id: str
    region: str
    issued_at: str
    valid_from: str
    valid_to: str
    hazard: str
    probability: float
    rainfall_mm: float = 0.0
    wind_kmh: float = 0.0
    river_level_m: float = 0.0
    uncertainty: float = 0.2
    source: str = "demo-forecast"
    confidence: float = 0.7
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelEntry:
    name: str
    version: str
    status: str = "deployed"  # deployed, shadow, retired
    metrics: dict[str, float] = field(default_factory=dict)
    deployed_at: str = field(default_factory=now_iso)
    rollback_to: str | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "ModelEntry":
        return cls(**payload)


@dataclass
class TenantPreferences:
    tenant: str
    channels: list[str] = field(default_factory=lambda: ["email", "slack"])
    quiet_hours: tuple[int, int] | None = (22, 7)
    digest: str = "instant"
    language: str = "en"
    alert_budget_per_day: int = 8
    recipients: list[dict] = field(default_factory=list)
    escalation_minutes: int = 30
    webhook_url: str | None = None
    paused: bool = False
    kill_switch: bool = False

    def __post_init__(self) -> None:
        if self.quiet_hours is not None:
            self.quiet_hours = tuple(self.quiet_hours)  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "TenantPreferences":
        return cls(**payload)


@dataclass
class CostEntry:
    id: str
    tenant: str
    scope_id: str
    kind: str  # imagery, inference, analyst
    amount_eur: float
    at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationRecord:
    scope_id: str
    analyst: str
    alert_id: str
    decision: str
    at: str = field(default_factory=now_iso)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def dumps(payload: dict | list) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(text: str) -> dict:
    return json.loads(text)


def add_hours(value: datetime, hours: float) -> str:
    return (value + timedelta(hours=hours)).isoformat(timespec="seconds")
