"""Environment-driven production configuration and a no-secret doctor."""

from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ROOT


def _load_dotenv() -> None:
    """Minimal .env loader: real environment always wins."""
    for candidate in (ROOT / ".env", ROOT.parent / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class LLMSettings:
    backend: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    provider: str = "openai"
    temperature: float = 0.2
    timeout: float = 60.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def safe(self) -> dict:
        return {"backend": self.backend, "baseUrl": self.base_url, "model": self.model or None, "configured": self.configured}


@dataclass
class InferenceSettings:
    model_path: str = str(ROOT / "models" / "damage-head.onnx")
    providers: str = "auto"
    batch_size: int = 8
    device: str = "auto"

    @property
    def configured(self) -> bool:
        return Path(self.model_path).exists()

    def safe(self) -> dict:
        return {"modelPath": self.model_path, "modelPresent": self.configured, "providers": self.providers, "batchSize": self.batch_size}


@dataclass
class ImagerySettings:
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    collection: str = "sentinel-2-l2a"
    max_cloud: float = 30.0
    cache_dir: str = str(ROOT / "runtime" / "imagery")
    planet_api_key: str = ""
    maxar_api_key: str = ""
    airbus_api_key: str = ""
    sftp_host: str = ""
    sftp_user: str = ""
    sftp_password: str = ""

    def safe(self) -> dict:
        return {
            "stac": self.stac_url,
            "collection": self.collection,
            "maxCloud": self.max_cloud,
            "cache": self.cache_dir,
            "planet": bool(self.planet_api_key),
            "maxar": bool(self.maxar_api_key),
            "airbus": bool(self.airbus_api_key),
            "sftp": bool(self.sftp_host),
        }


@dataclass
class ChannelSettings:
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "georesponse@example.com"
    smtp_tls: bool = True
    slack_webhook: str = ""
    teams_webhook: str = ""
    twilio_account_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = ""
    pagerduty_routing_key: str = ""
    generic_webhook: str = ""

    def safe(self) -> dict:
        return {
            "email": bool(self.smtp_host),
            "slack": bool(self.slack_webhook),
            "teams": bool(self.teams_webhook),
            "sms": bool(self.twilio_account_sid and self.twilio_token and self.twilio_from),
            "pager": bool(self.pagerduty_routing_key),
            "webhook": bool(self.generic_webhook),
        }


@dataclass
class IntegrationSettings:
    jira_url: str = ""
    jira_email: str = ""
    jira_token: str = ""
    jira_project: str = "GEO"
    servicenow_url: str = ""
    servicenow_user: str = ""
    servicenow_password: str = ""
    guidewire_url: str = ""
    guidewire_token: str = ""
    duckcreek_url: str = ""
    duckcreek_token: str = ""
    maximo_url: str = ""
    maximo_token: str = ""
    sap_url: str = ""
    sap_user: str = ""
    sap_password: str = ""
    arcgis_url: str = ""
    arcgis_token: str = ""
    siem_url: str = ""
    siem_token: str = ""

    def safe(self) -> dict:
        return {
            "jira": bool(self.jira_url and self.jira_token),
            "servicenow": bool(self.servicenow_url and self.servicenow_user),
            "guidewire": bool(self.guidewire_url and self.guidewire_token),
            "duckcreek": bool(self.duckcreek_url and self.duckcreek_token),
            "maximo": bool(self.maximo_url and self.maximo_token),
            "sap": bool(self.sap_url and self.sap_user),
            "arcgis": bool(self.arcgis_url and self.arcgis_token),
            "siem": bool(self.siem_url and self.siem_token),
        }


@dataclass
class PlatformSettings:
    postgres_dsn: str = ""
    redis_url: str = ""
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    auth_mode: str = "api-key"
    api_key: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""
    tenant: str = "demo"

    def safe(self) -> dict:
        return {
            "postgres": bool(self.postgres_dsn),
            "redis": bool(self.redis_url),
            "s3": bool(self.s3_bucket and self.s3_endpoint),
            "auth": self.auth_mode,
            "authConfigured": bool(self.api_key or (self.oidc_issuer and self.oidc_audience)),
            "tenant": self.tenant,
        }


@dataclass
class Settings:
    mode: str = "auto"
    llm: LLMSettings = field(default_factory=LLMSettings)
    inference: InferenceSettings = field(default_factory=InferenceSettings)
    imagery: ImagerySettings = field(default_factory=ImagerySettings)
    channels: ChannelSettings = field(default_factory=ChannelSettings)
    integrations: IntegrationSettings = field(default_factory=IntegrationSettings)
    platform: PlatformSettings = field(default_factory=PlatformSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=env("GEORESPONSE_MODE", "auto"),
            llm=LLMSettings(
                backend=env("GEORESPONSE_AGENT_BACKEND", "openai"),
                api_key=env("GEORESPONSE_LLM_API_KEY", env("API_KEY")),
                base_url=env("GEORESPONSE_LLM_BASE_URL", env("API_BASE", "https://api.openai.com/v1")),
                model=env("GEORESPONSE_LLM_MODEL", env("MODEL_NAME")),
                provider=env("GEORESPONSE_LLM_PROVIDER", env("MODEL_PROVIDER", "openai")),
                temperature=float(env("GEORESPONSE_LLM_TEMPERATURE", "0.2")),
                timeout=float(env("GEORESPONSE_LLM_TIMEOUT", "60")),
            ),
            inference=InferenceSettings(
                model_path=env("GEORESPONSE_ONNX_MODEL", str(ROOT / "models" / "damage-head.onnx")),
                providers=env("GEORESPONSE_ONNX_PROVIDERS", "auto"),
                batch_size=int(env("GEORESPONSE_ONNX_BATCH", "8")),
                device=env("GEORESPONSE_ONNX_DEVICE", "auto"),
            ),
            imagery=ImagerySettings(
                stac_url=env("GEORESPONSE_STAC_URL", "https://earth-search.aws.element84.com/v1"),
                collection=env("GEORESPONSE_STAC_COLLECTION", "sentinel-2-l2a"),
                max_cloud=float(env("GEORESPONSE_MAX_CLOUD", "30")),
                cache_dir=env("GEORESPONSE_IMAGERY_CACHE", str(ROOT / "runtime" / "imagery")),
                planet_api_key=env("PLANET_API_KEY"),
                maxar_api_key=env("MAXAR_API_KEY"),
                airbus_api_key=env("AIRBUS_API_KEY"),
                sftp_host=env("GEORESPONSE_SFTP_HOST"),
                sftp_user=env("GEORESPONSE_SFTP_USER"),
                sftp_password=env("GEORESPONSE_SFTP_PASSWORD"),
            ),
            channels=ChannelSettings(
                smtp_host=env("GEORESPONSE_SMTP_HOST"),
                smtp_port=int(env("GEORESPONSE_SMTP_PORT", "587")),
                smtp_user=env("GEORESPONSE_SMTP_USER"),
                smtp_password=env("GEORESPONSE_SMTP_PASSWORD"),
                smtp_from=env("GEORESPONSE_SMTP_FROM", "georesponse@example.com"),
                smtp_tls=env_bool("GEORESPONSE_SMTP_TLS", True),
                slack_webhook=env("GEORESPONSE_SLACK_WEBHOOK"),
                teams_webhook=env("GEORESPONSE_TEAMS_WEBHOOK"),
                twilio_account_sid=env("TWILIO_ACCOUNT_SID"),
                twilio_token=env("TWILIO_AUTH_TOKEN"),
                twilio_from=env("TWILIO_FROM"),
                pagerduty_routing_key=env("PAGERDUTY_ROUTING_KEY"),
                generic_webhook=env("GEORESPONSE_WEBHOOK_URL"),
            ),
            integrations=IntegrationSettings(
                jira_url=env("JIRA_URL"),
                jira_email=env("JIRA_EMAIL"),
                jira_token=env("JIRA_API_TOKEN"),
                jira_project=env("JIRA_PROJECT", "GEO"),
                servicenow_url=env("SERVICENOW_URL"),
                servicenow_user=env("SERVICENOW_USER"),
                servicenow_password=env("SERVICENOW_PASSWORD"),
                guidewire_url=env("GUIDEWIRE_URL"),
                guidewire_token=env("GUIDEWIRE_TOKEN"),
                duckcreek_url=env("DUCK_CREEK_URL"),
                duckcreek_token=env("DUCK_CREEK_TOKEN"),
                maximo_url=env("MAXIMO_URL"),
                maximo_token=env("MAXIMO_TOKEN"),
                sap_url=env("SAP_URL"),
                sap_user=env("SAP_USER"),
                sap_password=env("SAP_PASSWORD"),
                arcgis_url=env("ARCGIS_URL"),
                arcgis_token=env("ARCGIS_TOKEN"),
                siem_url=env("SIEM_HEC_URL"),
                siem_token=env("SIEM_HEC_TOKEN"),
            ),
            platform=PlatformSettings(
                postgres_dsn=env("GEORESPONSE_POSTGRES_DSN"),
                redis_url=env("GEORESPONSE_REDIS_URL"),
                s3_endpoint=env("GEORESPONSE_S3_ENDPOINT"),
                s3_bucket=env("GEORESPONSE_S3_BUCKET"),
                s3_access_key=env("GEORESPONSE_S3_ACCESS_KEY"),
                s3_secret_key=env("GEORESPONSE_S3_SECRET_KEY"),
                auth_mode=env("GEORESPONSE_AUTH_MODE", "api-key"),
                api_key=env("GEORESPONSE_API_KEY"),
                oidc_issuer=env("GEORESPONSE_OIDC_ISSUER"),
                oidc_audience=env("GEORESPONSE_OIDC_AUDIENCE"),
                tenant=env("GEORESPONSE_TENANT", "demo"),
            ),
        )

    def safe(self) -> dict:
        return {
            "mode": self.mode,
            "llm": self.llm.safe(),
            "inference": self.inference.safe(),
            "imagery": self.imagery.safe(),
            "channels": self.channels.safe(),
            "integrations": self.integrations.safe(),
            "platform": self.platform.safe(),
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def doctor(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    add("LLM agent", settings.llm.configured, "API key + model" if settings.llm.configured else "set GEORESPONSE_LLM_API_KEY and GEORESPONSE_LLM_MODEL", True)
    add("ONNX model", settings.inference.configured, settings.inference.model_path, True)
    try:
        import onnxruntime as ort  # noqa: F401

        add("ONNX Runtime", True, "installed", True)
    except Exception:
        add("ONNX Runtime", False, "pip install onnxruntime", True)
    try:
        import rasterio  # noqa: F401

        add("Rasterio", True, "installed", True)
    except Exception:
        add("Rasterio", False, "pip install rasterio", True)
    channels = settings.channels.safe()
    add("Email", channels["email"], "SMTP_*", False)
    add("Slack", channels["slack"], "GEORESPONSE_SLACK_WEBHOOK", False)
    add("Teams", channels["teams"], "GEORESPONSE_TEAMS_WEBHOOK", False)
    add("SMS", channels["sms"], "TWILIO_*", False)
    add("Webhook", channels["webhook"], "GEORESPONSE_WEBHOOK_URL", False)
    add("PostgreSQL", settings.platform.safe()["postgres"], "GEORESPONSE_POSTGRES_DSN", False)
    add("Object storage", settings.platform.safe()["s3"], "S3 endpoint + bucket", False)
    add("Authentication", settings.platform.safe()["authConfigured"], "API key or OIDC", False)
    try:
        from .queue import health as redis_health

        redis = redis_health(settings.platform)
        add("Redis queue", bool(redis.get("ok")), redis.get("detail", "configured"), False)
    except Exception as exc:
        add("Redis queue", False, str(exc), False)
    try:
        from .storage import health as storage_health

        storage = storage_health(settings.platform)
        add("S3 object store", bool(storage.get("ok")), storage.get("detail", "configured"), False)
    except Exception as exc:
        add("S3 object store", False, str(exc), False)
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        npu = [name for name in providers if name in {"CANNExecutionProvider", "OpenVINOExecutionProvider", "QNNExecutionProvider", "VitisAIExecutionProvider"}]
        add("NPU provider", bool(npu), f"available: {npu or providers}", False)
    except Exception as exc:
        add("NPU provider", False, str(exc), False)
    add("Disk", shutil.disk_usage(ROOT).free > 1_000_000_000, "> 1 GB free", True)
    try:
        socket.create_connection(("earth-search.aws.element84.com", 443), timeout=4).close()
        add("STAC network", True, "earth-search reachable", False)
    except Exception as exc:  # noqa: BLE001
        add("STAC network", False, str(exc), False)
    required = [check for check in checks if check["required"]]
    return {
        "mode": settings.mode,
        "ready": all(check["ok"] for check in required),
        "checks": checks,
        "settings": settings.safe(),
        "note": "Secrets are never returned. A red optional check disables only that channel.",
    }
