"""API authentication: API key or OIDC bearer token.

When no authentication is configured the API is loopback/demo-only.  Production
deployments set ``GEORESPONSE_API_KEY`` or OIDC issuer/audience.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import PlatformSettings, get_settings


class AuthError(PermissionError):
    pass


@dataclass
class Principal:
    subject: str
    tenant: str
    role: str
    method: str


_jwks_cache: dict[str, dict] = {}


def _jwks(issuer: str) -> dict:
    if issuer in _jwks_cache:
        return _jwks_cache[issuer]
    response = httpx.get(issuer.rstrip("/") + "/.well-known/jwks.json", timeout=15)
    response.raise_for_status()
    _jwks_cache[issuer] = response.json()
    return _jwks_cache[issuer]


def authenticate(headers: dict, settings: PlatformSettings | None = None) -> Principal:
    settings = settings or get_settings().platform
    if settings.auth_mode == "api-key" and settings.api_key:
        supplied = headers.get("x-api-key") or headers.get("authorization", "").removeprefix("Bearer ")
        if supplied != settings.api_key:
            raise AuthError("invalid API key")
        return Principal(subject="api-key", tenant=settings.tenant, role="admin", method="api-key")
    if settings.auth_mode == "oidc":
        if not (settings.oidc_issuer and settings.oidc_audience):
            raise AuthError("OIDC is not configured")
        token = headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not token:
            raise AuthError("missing bearer token")
        try:
            import jwt
            from jwt import PyJWKClient

            signing_key = PyJWKClient(settings.oidc_issuer.rstrip("/") + "/.well-known/jwks.json").get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=["RS256"], audience=settings.oidc_audience, issuer=settings.oidc_issuer)
        except Exception as exc:  # noqa: BLE001
            raise AuthError(f"invalid token: {exc}") from exc
        tenant = str(payload.get("tenant") or payload.get("org") or settings.tenant)
        return Principal(subject=str(payload.get("sub", "oidc")), tenant=tenant, role=str(payload.get("role", "analyst")), method="oidc")
    return Principal(subject="anonymous", tenant=settings.tenant, role="demo", method="none")


def configured(settings: PlatformSettings | None = None) -> bool:
    settings = settings or get_settings().platform
    return bool(settings.api_key or (settings.oidc_issuer and settings.oidc_audience))
