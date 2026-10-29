"""Tenant isolation and privacy review artefacts.

The demo is single-tenant, but every storage path is tenant-scoped from day one
so the multi-customer phase does not need a data migration.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class TenantError(PermissionError):
    pass


class TenantStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", tenant):
            raise TenantError("invalid tenant id")
        return self.root / tenant

    def ensure(self, tenant: str) -> Path:
        path = self._path(tenant)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write(self, tenant: str, relative: str, payload: dict) -> Path:
        base = self._path(tenant)
        target = (base / relative).resolve()
        if base.resolve() not in target.parents and target.parent != base.resolve():
            raise TenantError("path escapes tenant root")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def read(self, tenant: str, relative: str) -> dict:
        base = self._path(tenant)
        target = (base / relative).resolve()
        if base.resolve() not in target.parents and target.parent != base.resolve():
            raise TenantError("path escapes tenant root")
        return json.loads(target.read_text(encoding="utf-8"))

    def list_tenants(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())


def assert_isolation(store: TenantStore, tenant: str, relative: str) -> bool:
    try:
        store.read(tenant, relative)
        return True
    except (FileNotFoundError, TenantError):
        return False


PRIVACY_CHECKLIST = [
    ("lawful_basis", "Document the lawful basis for processing aerial imagery of residential property."),
    ("minimisation", "Crop residential imagery to the insured property footprint before model inference."),
    ("redaction", "Blur faces, vehicles and private gardens in exported evidence where not required for the claim."),
    ("retention", "Set a retention clock per event; delete raw imagery after the claim decision plus the legal minimum."),
    ("access", "Role-based access: analyst, reviewer, auditor, customer. No shared accounts."),
    ("dpa", "Sign a data-processing agreement and list every subprocessor, including the NPU vendor."),
    ("sovereignty", "Offer on-site or private-cloud inference; no outbound network after imagery delivery."),
    ("transparency", "Customer-facing notice explains AI assistance and the human decision."),
    ("human_review", "No automated decision about people or property; an analyst signs every assessment."),
    ("incident", "Breach playbook with 72-hour notification and an audit-trail export."),
]


def privacy_review(completed: set[str] | None = None) -> dict:
    completed = completed or set()
    items = [
        {"id": key, "requirement": text, "status": "done" if key in completed else "open"}
        for key, text in PRIVACY_CHECKLIST
    ]
    return {
        "policy": "Privacy review for residential aerial imagery",
        "items": items,
        "open": sum(1 for i in items if i["status"] == "open"),
        "done": sum(1 for i in items if i["status"] == "done"),
        "note": "This is an engineering checklist, not legal advice. Legal review is a pilot gate.",
    }


def redact_pii(payload: dict, keys: tuple[str, ...] = ("holder", "address", "email", "phone", "claimRef")) -> dict:
    out = json.loads(json.dumps(payload))
    for key in keys:
        if key in out:
            value = str(out[key])
            out[key] = value[:2] + "***" if len(value) > 2 else "***"
    return out


def deployment_manifest() -> dict:
    return {
        "targets": ["docker-compose", "linux-on-prem", "private-cloud", "edge-npu"],
        "network": "no outbound network required after imagery delivery",
        "components": ["web (static)", "pipeline (python)", "optional API", "optional NPU broker"],
        "dataSovereignty": "imagery and model stay inside the customer network",
        "backup": "append-only audit log + assessment JSON, encrypted at rest",
    }
