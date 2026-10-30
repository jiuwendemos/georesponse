"""Agent proposals with server-side approval, rejection and undo.

The model never mutates an alert. It creates a proposal; a named human approves
it through the API, which applies the change and records the previous state so
it can be undone. This keeps approval enforceable outside the browser.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from . import alerts as alert_ops
from .models import now_iso, new_id, parse_iso
from .store import ProactiveStore

ACTIONS = {"assign", "dismiss", "handoff"}


@dataclass
class Proposal:
    id: str
    tenant: str
    alert_id: str
    action: str
    payload: dict
    status: str = "pending"  # pending, approved, rejected, undone
    created_at: str = field(default_factory=now_iso)
    expires_at: str | None = None
    created_by: str = "agent"
    decided_by: str | None = None
    decided_at: str | None = None
    previous: dict | None = None
    result: dict | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProposalError(ValueError):
    pass


class ProposalStore:
    def __init__(self, store: ProactiveStore, *, ttl_minutes: int = 60) -> None:
        self.store = store
        self.ttl_minutes = ttl_minutes

    def _key(self, proposal_id: str) -> str:
        return f"proposal:{proposal_id}"

    def create(self, *, tenant: str, alert_id: str, action: str, payload: dict, created_by: str = "agent") -> Proposal:
        if action not in ACTIONS:
            raise ProposalError(f"unsupported proposal action: {action}")
        if self.store.get_alert(alert_id) is None:
            raise ProposalError(f"unknown alert {alert_id}")
        proposal = Proposal(
            id=new_id("PROP"),
            tenant=tenant,
            alert_id=alert_id,
            action=action,
            payload=payload,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=self.ttl_minutes)).isoformat(timespec="seconds"),
            created_by=created_by,
        )
        self.store.meta_set(self._key(proposal.id), json.dumps(proposal.to_dict(), ensure_ascii=False))
        self.store.audit(tenant, "proposal.created", alert_id=alert_id, actor=created_by, detail={"proposal": proposal.id, "action": action})
        return proposal

    def get(self, proposal_id: str) -> Proposal:
        raw = self.store.meta_get(self._key(proposal_id))
        if not raw:
            raise ProposalError(f"unknown proposal {proposal_id}")
        return Proposal(**json.loads(raw))

    def _save(self, proposal: Proposal) -> Proposal:
        self.store.meta_set(self._key(proposal.id), json.dumps(proposal.to_dict(), ensure_ascii=False))
        return proposal

    def pending(self, tenant: str) -> list[Proposal]:
        # Meta keys are not enumerable through the store interface, so the
        # proposal index is kept as a JSON list.
        raw = self.store.meta_get(f"proposals:{tenant}")
        ids = json.loads(raw) if raw else []
        items = []
        for proposal_id in ids:
            try:
                proposal = self.get(proposal_id)
            except ProposalError:
                continue
            if proposal.status == "pending":
                items.append(proposal)
        return items

    def _index(self, proposal: Proposal) -> None:
        key = f"proposals:{proposal.tenant}"
        raw = self.store.meta_get(key)
        ids = json.loads(raw) if raw else []
        if proposal.id not in ids:
            ids.append(proposal.id)
        self.store.meta_set(key, json.dumps(ids[-500:]))

    def approve(self, proposal_id: str, *, actor: str) -> dict:
        proposal = self.get(proposal_id)
        if proposal.status != "pending":
            raise ProposalError(f"proposal is {proposal.status}")
        if proposal.expires_at and parse_iso(proposal.expires_at) < datetime.now(timezone.utc):
            proposal.status = "rejected"
            proposal.note = "expired"
            self._save(proposal)
            raise ProposalError("proposal expired")
        alert = self.store.get_alert(proposal.alert_id)
        if alert is None:
            raise ProposalError("alert no longer exists")
        proposal.previous = {"status": alert.status, "assignee": alert.assignee, "dismissed_reason": alert.dismissed_reason}
        if proposal.action == "assign":
            alert_ops.transition(self.store, alert.id, "assign", actor=actor, assignee=proposal.payload.get("team") or actor, note=proposal.payload.get("note", ""))
            proposal.result = {"status": "assigned", "assignee": proposal.payload.get("team")}
        elif proposal.action == "dismiss":
            alert_ops.transition(self.store, alert.id, "dismiss", actor=actor, reason=proposal.payload.get("reason"), note=proposal.payload.get("note", ""))
            proposal.result = {"status": "dismissed", "reason": proposal.payload.get("reason")}
        else:  # handoff
            proposal.result = {"draft": proposal.payload.get("target"), "sent": False}
        proposal.status = "approved"
        proposal.decided_by = actor
        proposal.decided_at = now_iso()
        self._index(proposal)
        self._save(proposal)
        self.store.audit(proposal.tenant, "proposal.approved", alert_id=alert.id, actor=actor, detail={"proposal": proposal.id, "action": proposal.action})
        return proposal.to_dict()

    def reject(self, proposal_id: str, *, actor: str, reason: str = "") -> dict:
        proposal = self.get(proposal_id)
        if proposal.status != "pending":
            raise ProposalError(f"proposal is {proposal.status}")
        proposal.status = "rejected"
        proposal.decided_by = actor
        proposal.decided_at = now_iso()
        proposal.note = reason
        self._index(proposal)
        self._save(proposal)
        self.store.audit(proposal.tenant, "proposal.rejected", alert_id=proposal.alert_id, actor=actor, detail={"proposal": proposal.id, "reason": reason})
        return proposal.to_dict()

    def undo(self, proposal_id: str, *, actor: str) -> dict:
        proposal = self.get(proposal_id)
        if proposal.status != "approved" or not proposal.previous:
            raise ProposalError("only an approved proposal with a stored prior state can be undone")
        alert = self.store.get_alert(proposal.alert_id)
        if alert is None:
            raise ProposalError("alert no longer exists")
        alert.status = proposal.previous.get("status", alert.status)
        alert.assignee = proposal.previous.get("assignee")
        alert.dismissed_reason = proposal.previous.get("dismissed_reason")
        alert.updated_at = now_iso()
        self.store.save_alert(alert)
        proposal.status = "undone"
        proposal.decided_by = actor
        proposal.decided_at = now_iso()
        self._save(proposal)
        self.store.audit(proposal.tenant, "proposal.undone", alert_id=alert.id, actor=actor, detail={"proposal": proposal.id})
        return proposal.to_dict()
