"""Feature-flagged facade between GeoResponse triage and the LAIX core.

Modes:

* ``native`` - the app's existing urgency/SLA rules decide; LAIX is not called.
* ``shadow`` - both decide, native stays authoritative, parity is recorded.
* ``laix``   - LAIX decides; native is still computed so a rollback is a flag
  flip and parity keeps being measured.

The default is ``native`` so an existing deployment never changes behaviour on
upgrade.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

from laix import SCHEMA_VERSION, Decision, DecisionRuntime, ExperienceState, iso

from ..proactive.models import Alert, MonitoringPlan
from ..proactive.store import ProactiveStore
from .approval_bridge import ApprovalBridge
from .spatial_context import (
    DEFAULT_ANALYSTS,
    compare,
    laix_view,
    native_triage,
    options_for_alert,
    situation_from_alert,
)

ENV_FLAG = "GEORESPONSE_DECISION_ENGINE"
MODES = ("native", "shadow", "laix")
DEFAULT_MODE = "native"
PARITY_KEY = "laix:parity"


def configured_mode() -> str:
    raw = (os.environ.get(ENV_FLAG) or DEFAULT_MODE).strip().lower()
    return raw if raw in MODES else DEFAULT_MODE


def _empty_parity() -> dict:
    return {
        "samples": 0,
        "agreements": 0,
        "mismatches": 0,
        "agreementRate": None,
        "byVerb": {},
        "recent": [],
        "lastAt": None,
    }


class DecisionEngineFacade:
    def __init__(self, store: ProactiveStore, *, mode: str | None = None) -> None:
        self.store = store
        self.mode = mode or configured_mode()
        if self.mode not in MODES:
            raise ValueError(f"unknown decision-engine mode: {self.mode}")
        self.runtime = DecisionRuntime(state=ExperienceState(subject="georesponse"))
        self.approvals = ApprovalBridge(store)
        for name, handler in self.approvals.execution_handlers().items():
            self.runtime.bridge.register(name, handler)

    # ------------------------------------------------------------------ triage
    def triage(
        self,
        alert: Alert,
        *,
        plan: MonitoringPlan | None = None,
        analysts: Iterable[str] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        plan = plan or MonitoringPlan(scope_id=alert.scope_id)
        roster = list(analysts) if analysts is not None else None
        native = native_triage(alert, plan=plan, analysts=roster)
        if self.mode == "native":
            return {
                "mode": self.mode,
                "authoritativeSource": "native",
                "native": native,
                "laix": None,
                "parity": None,
                "decision": None,
            }

        situation = situation_from_alert(alert, plan=plan, analysts=roster)
        options = options_for_alert(alert, plan=plan, analysts=roster)
        decision = self.runtime.decide(situation, options)
        action = next((item for item in options if item.id == decision.action_id), None)
        laix = laix_view(decision, action=action, alert=alert)
        parity = compare(native, laix)
        authoritative = laix if self.mode == "laix" else native

        if persist:
            self._record_parity(alert, native, laix, parity)
            if self.mode == "laix":
                self.store.audit(
                    alert.tenant,
                    "laix.decision",
                    alert_id=alert.id,
                    actor="laix",
                    detail={
                        "verb": decision.verb,
                        "action": decision.action_id,
                        "rationale": decision.rationale,
                        "parity": parity["agrees"],
                    },
                )

        return {
            "mode": self.mode,
            "authoritativeSource": "laix" if self.mode == "laix" else "native",
            "native": native,
            "laix": laix,
            "parity": parity,
            "decision": decision.to_dict(),
            "authoritative": authoritative,
        }

    # ------------------------------------------------------------------ status
    def status(self, tenant: str = "demo") -> dict[str, Any]:
        parity = self._load_parity(tenant)
        return {
            "mode": self.mode,
            "flag": ENV_FLAG,
            "modes": list(MODES),
            "policyVersion": self.runtime.policy.version,
            "schemaVersion": SCHEMA_VERSION,
            "models": ["change_confirmed"],
            "parity": parity,
            "runtime": self.runtime.stats(),
        }

    def evaluate(
        self,
        alert: Alert,
        *,
        plan: MonitoringPlan | None = None,
        analysts: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Run both engines without writing parity or touching runtime state."""
        plan = plan or MonitoringPlan(scope_id=alert.scope_id)
        roster = list(analysts) if analysts is not None else None
        native = native_triage(alert, plan=plan, analysts=roster)
        situation = situation_from_alert(alert, plan=plan, analysts=roster)
        options = options_for_alert(alert, plan=plan, analysts=roster)
        decision = DecisionRuntime().decide(situation, options)
        action = next((item for item in options if item.id == decision.action_id), None)
        laix = laix_view(decision, action=action, alert=alert)
        return {"native": native, "laix": laix, "parity": compare(native, laix), "decision": decision.to_dict()}

    def evaluate_all(self, tenant: str = "demo") -> dict[str, Any]:
        rows = []
        for alert in self.store.list_alerts(tenant):
            if alert.status in {"resolved", "dismissed"}:
                continue
            plan = self.store.get_plan(alert.scope_id)
            result = self.evaluate(alert, plan=plan)
            rows.append({"alertId": alert.id, **result})
        disagreements = [row for row in rows if not row["parity"]["agrees"]]
        return {
            "tenant": tenant,
            "samples": len(rows),
            "agreements": len(rows) - len(disagreements),
            "agreementRate": round((len(rows) - len(disagreements)) / max(1, len(rows)), 4),
            "disagreements": [
                {
                    "alertId": row["alertId"],
                    "nativeVerb": row["native"]["verb"],
                    "laixVerb": row["laix"]["verb"],
                    "differences": row["parity"]["differences"],
                }
                for row in disagreements[:25]
            ],
            "evaluatedAt": iso(),
        }

    def parity(self, tenant: str = "demo") -> dict[str, Any]:
        return self._load_parity(tenant)

    def reset_parity(self, tenant: str = "demo") -> dict[str, Any]:
        self.store.meta_set(f"{PARITY_KEY}:{tenant}", json.dumps(_empty_parity(), ensure_ascii=False))
        return _empty_parity()

    def _record_parity(self, alert: Alert, native: dict, laix: dict, parity: dict) -> None:
        record = self._load_parity(alert.tenant)
        record["samples"] += 1
        if parity["agrees"]:
            record["agreements"] += 1
        else:
            record["mismatches"] += 1
            entry = {
                "at": iso(),
                "alertId": alert.id,
                "severity": alert.severity,
                "nativeVerb": native["verb"],
                "laixVerb": laix["verb"],
                "differences": parity["differences"],
            }
            record["recent"] = ([entry] + record["recent"])[:20]
        key = f"{native['verb']}->{laix['verb']}"
        record["byVerb"][key] = int(record["byVerb"].get(key, 0)) + 1
        record["agreementRate"] = round(record["agreements"] / max(1, record["samples"]), 4)
        record["lastAt"] = iso()
        self.store.meta_set(f"{PARITY_KEY}:{alert.tenant}", json.dumps(record, ensure_ascii=False))

    def _load_parity(self, tenant: str) -> dict:
        raw = self.store.meta_get(f"{PARITY_KEY}:{tenant}")
        if not raw:
            return _empty_parity()
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            return _empty_parity()
        merged = _empty_parity()
        merged.update(record if isinstance(record, dict) else {})
        return merged

    # --------------------------------------------------------------- execution
    def execute(
        self,
        decision: Decision,
        *,
        actor: str,
        approver: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt = self.runtime.execute(decision, actor=actor, approver=approver, context=context or {"actor": actor})
        return receipt.to_dict()

    def propose(
        self,
        decision: Decision,
        action,
        *,
        alert_id: str,
        payload: dict[str, Any] | None = None,
        created_by: str = "laix",
    ) -> dict[str, Any]:
        return self.approvals.propose(decision, action, alert_id=alert_id, payload=payload, created_by=created_by)


_FACADES: dict[tuple[int, str], DecisionEngineFacade] = {}


def get_facade(store: ProactiveStore, *, mode: str | None = None) -> DecisionEngineFacade:
    """One facade per (store, mode) so parity counters survive requests."""
    resolved = mode or configured_mode()
    key = (id(store), resolved)
    facade = _FACADES.get(key)
    if facade is None:
        facade = DecisionEngineFacade(store, mode=resolved)
        _FACADES[key] = facade
    return facade


def reset_facades() -> None:
    _FACADES.clear()
