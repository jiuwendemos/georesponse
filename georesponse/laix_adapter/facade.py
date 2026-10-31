"""The only decision path in GeoResponse: alert in, LAIX decision out.

GeoResponse owns the alert, imagery, SLA, analyst roster, proposal registry and
approval.  LAIX owns the generic decision.  There is no second policy and no
runtime switch.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Iterable

from laix import SCHEMA_VERSION, Action, DecisionRequest, Layer, LayerDecision

from ..proactive.models import Alert, MonitoringPlan
from ..proactive.store import ProactiveStore
from .approval_bridge import ApprovalBridge
from .spatial_context import laix_view, options_for_alert, situation_from_alert


def _package_version() -> str:
    try:
        return version("laix")
    except PackageNotFoundError:  # pragma: no cover - installed in every real run
        return "unknown"


class DecisionEngineFacade:
    def __init__(self, store: ProactiveStore) -> None:
        self.store = store
        self.layer = Layer()
        self.approvals = ApprovalBridge(store)
        for name, handler in self.approvals.execution_handlers().items():
            self.layer.bridge().register(name, handler)
        self._decisions: dict[str, Any] = {}
        self._actions: dict[str, Action | None] = {}

    # ------------------------------------------------------------------ decide
    def triage(
        self,
        alert: Alert,
        *,
        plan: MonitoringPlan | None = None,
        analysts: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        plan = plan or MonitoringPlan(scope_id=alert.scope_id)
        roster = list(analysts) if analysts is not None else None
        situation = situation_from_alert(alert, plan=plan, analysts=roster)
        options = options_for_alert(alert, plan=plan, analysts=roster)
        decision = self.layer.decide(
            DecisionRequest(
                subject=alert.id,
                at=situation.at,
                situation=situation,
                options=options,
            )
        )[0]
        action = next((item for item in options if item.id == decision.action_id), None)
        self._decisions[decision.decision_id] = decision
        self._actions[decision.decision_id] = action
        view = laix_view(decision, action=action, alert=alert)
        self.store.audit(
            alert.tenant,
            "laix.decision",
            alert_id=alert.id,
            actor="laix",
            detail={
                "verb": decision.verb,
                "action": decision.action_id,
                "reason": decision.reason_code,
                "rationale": decision.rationale,
                "policy": decision.policy_version,
            },
        )
        return {
            "engine": "laix",
            "laix": view,
            "decision": decision.to_dict(),
        }

    # ------------------------------------------------------------------ apply
    def apply(self, alert: Alert, triage: dict[str, Any]) -> Alert:
        """Apply the LAIX verb to the alert's working state.

        An alert that LAIX does not think is worth acting on must not keep an
        implied owner.  A breached deadline is tagged for the on-call lead.
        """
        verb = triage.get("laix", {}).get("verb")
        if verb in {"wait", "observe", "ask", "guide"}:
            alert.assignee = None
        elif verb == "escalate":
            alert.tags = list(dict.fromkeys([*alert.tags, "sla-escalated"]))
        return alert

    # ----------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        return {
            "engine": "laix",
            "package": "laix",
            "packageVersion": _package_version(),
            "policyVersion": self.layer.runtime.policy.version,
            "schemaVersion": SCHEMA_VERSION,
        }

    def decision(self, decision_id: str) -> LayerDecision:
        return self._decisions[decision_id]

    def action(self, decision_id: str) -> Action | None:
        return self._actions.get(decision_id)

    # -------------------------------------------------------------- execution
    def execute(
        self,
        decision: LayerDecision,
        *,
        actor: str,
        approver: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # LAIX owns the approval gate and the receipt; GeoResponse owns the
        # handler registered on the bridge.  ``context`` is retained for
        # adapter callers but LAIX executes through the registered handler.
        receipt = self.layer.execute(decision, actor=actor, approver=approver)
        return receipt.to_dict()

    def propose(
        self,
        decision: LayerDecision,
        action: Action,
        *,
        alert_id: str,
        payload: dict[str, Any] | None = None,
        created_by: str = "laix",
    ) -> dict[str, Any]:
        return self.approvals.propose(decision, action, alert_id=alert_id, payload=payload, created_by=created_by)


_FACADES: dict[int, DecisionEngineFacade] = {}


def get_facade(store: ProactiveStore) -> DecisionEngineFacade:
    key = id(store)
    facade = _FACADES.get(key)
    if facade is None:
        facade = DecisionEngineFacade(store)
        _FACADES[key] = facade
    return facade
