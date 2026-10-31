"""Bridge LAIX approval-gated actions to GeoResponse's proposal registry.

LAIX's execution bridge knows *that* an action needs approval.  GeoResponse's
``ProposalStore`` knows *how* approval is recorded, expires and is undone.
This adapter is the seam: it creates a proposal from a decision, and it exposes
the handlers the bridge may call once a named human has approved.
"""

from __future__ import annotations

from typing import Any

from laix import Action, Decision

from ..proactive import alerts as alert_ops
from ..proactive.proposals import ProposalStore
from ..proactive.store import ProactiveStore

PROPOSAL_ACTION = {
    "assign_alert": "assign",
    "dismiss_alert": "dismiss",
    "handoff_alert": "handoff",
}


class ApprovalBridge:
    def __init__(self, store: ProactiveStore, *, ttl_minutes: int = 60) -> None:
        self.store = store
        self.proposals = ProposalStore(store, ttl_minutes=ttl_minutes)

    # ------------------------------------------------------------------ create
    def propose(
        self,
        decision: Decision,
        action: Action | None,
        *,
        alert_id: str,
        payload: dict[str, Any] | None = None,
        created_by: str = "laix",
    ) -> dict[str, Any]:
        if action is None:
            raise ValueError("a proposal needs a concrete action")
        proposal_action = PROPOSAL_ACTION.get(action.name)
        if proposal_action is None:
            raise ValueError(f"{action.name} is not a proposal-backed action")
        body = dict(payload or self._payload(action))
        proposal = self.proposals.create(
            tenant=str(action.params.get("tenant", "demo")),
            alert_id=alert_id,
            action=proposal_action,
            payload=body,
            created_by=created_by,
        )
        return {
            "proposal": proposal.to_dict(),
            "decision": decision.to_dict(),
            "requiresApproval": True,
        }

    @staticmethod
    def _payload(action: Action) -> dict[str, Any]:
        if action.name == "assign_alert":
            return {
                "team": action.params.get("assignee") or action.params.get("team"),
                "note": "LAIX triage: assign an owner",
            }
        if action.name == "handoff_alert":
            return {"target": action.params.get("target", "assessment")}
        if action.name == "dismiss_alert":
            return {"reason": action.params.get("reason", "false-positive"), "note": "LAIX triage: dismiss"}
        return dict(action.params)

    # ---------------------------------------------------------------- execute
    def execution_handlers(self) -> dict[str, Any]:
        """Handlers for ``laix.ExecutionBridge``.

        These perform the write.  They are only reached after the bridge has an
        approver; ordinary callers should use ``propose`` instead.
        """
        return {
            "assign_alert": self._assign,
            "handoff_alert": self._handoff,
            "dismiss_alert": self._dismiss,
        }

    def _assign(self, action: Action, context: dict[str, Any]) -> dict[str, Any]:
        alert_id = str(action.params["alert_id"])
        actor = str(context.get("actor", "laix-approved"))
        assignee = action.params.get("assignee") or action.params.get("team")
        updated = alert_ops.transition(self.store, alert_id, "assign", actor=actor, assignee=assignee)
        return {"alertId": alert_id, "status": updated.status, "assignee": updated.assignee}

    def _handoff(self, action: Action, context: dict[str, Any]) -> dict[str, Any]:
        # A handoff is a draft in the target system; GeoResponse does not send
        # claims or dispatch crews on its own.
        return {
            "alertId": str(action.params["alert_id"]),
            "draft": action.params.get("target", "assessment"),
            "sent": False,
            "actor": str(context.get("actor", "laix-approved")),
        }

    def _dismiss(self, action: Action, context: dict[str, Any]) -> dict[str, Any]:
        alert_id = str(action.params["alert_id"])
        actor = str(context.get("actor", "laix-approved"))
        reason = str(action.params.get("reason", "false-positive"))
        updated = alert_ops.transition(self.store, alert_id, "dismiss", actor=actor, reason=reason)
        return {"alertId": alert_id, "status": updated.status, "reason": updated.dismissed_reason}
