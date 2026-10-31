"""Execution bridge: approval, execution, cancellation, recovery and receipts.

LAIX decides; the host executes.  The bridge is a thin, auditable state machine
around named host skills.  It never imports a platform SDK and never performs
domain work itself.

Failure paths that matter (from ``interfaces.md``): the platform refuses, the
action hangs, the situation changes, or a human rejects the request.
"""

from __future__ import annotations

from typing import Any, Callable

from .contracts import Action, Decision, Receipt, new_receipt_id

Handler = Callable[[Action, dict[str, Any]], dict[str, Any]]


class ApprovalRequired(RuntimeError):
    """Raised when a destructive decision has no approver."""


class UnknownAction(RuntimeError):
    """Raised when a decision names an option the bridge cannot execute."""


class ExecutionBridge:
    def __init__(self, *, handlers: dict[str, Handler] | None = None, undo_handlers: dict[str, Handler] | None = None) -> None:
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self.undo_handlers: dict[str, Handler] = dict(undo_handlers or {})
        self.receipts: dict[str, Receipt] = {}

    def register(self, name: str, handler: Handler, *, undo: Handler | None = None) -> None:
        self.handlers[name] = handler
        if undo is not None:
            self.undo_handlers[name] = undo

    def can_handle(self, name: str) -> bool:
        return name in self.handlers

    def execute(
        self,
        decision: Decision,
        *,
        action: Action | None,
        actor: str,
        approver: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Receipt:
        if action is None:
            return self._store(
                Receipt(
                    id=new_receipt_id(),
                    decision_id=decision.id,
                    action_name="",
                    status="refused",
                    actor=actor,
                    error="decision has no action to execute",
                )
            )
        if decision.requires_approval and not approver:
            raise ApprovalRequired(f"{action.name} requires human approval")
        if not self.can_handle(action.name):
            return self._store(
                Receipt(
                    id=new_receipt_id(),
                    decision_id=decision.id,
                    action_name=action.name,
                    status="failed",
                    actor=actor,
                    error=f"no handler registered for {action.name}",
                    approved_by=approver,
                )
            )
        try:
            detail = self.handlers[action.name](action, dict(context or {})) or {}
        except Exception as exc:  # noqa: BLE001 - a failed action is data, not a crash
            return self._store(
                Receipt(
                    id=new_receipt_id(),
                    decision_id=decision.id,
                    action_name=action.name,
                    status="failed",
                    actor=actor,
                    error=f"{type(exc).__name__}: {exc}",
                    approved_by=approver,
                )
            )
        return self._store(
            Receipt(
                id=new_receipt_id(),
                decision_id=decision.id,
                action_name=action.name,
                status="executed",
                actor=actor,
                detail=detail,
                approved_by=approver,
            )
        )

    def refuse(self, decision: Decision, *, action: Action | None, actor: str, reason: str) -> Receipt:
        return self._store(
            Receipt(
                id=new_receipt_id(),
                decision_id=decision.id,
                action_name=action.name if action else "",
                status="refused",
                actor=actor,
                error=reason,
            )
        )

    def cancel(self, receipt_id: str, *, actor: str, reason: str = "") -> Receipt:
        receipt = self.get(receipt_id)
        if receipt.status not in {"pending", "approved"}:
            raise ValueError(f"cannot cancel a receipt that is {receipt.status}")
        cancelled = Receipt(
            id=receipt.id,
            decision_id=receipt.decision_id,
            action_name=receipt.action_name,
            status="cancelled",
            actor=actor,
            detail={**receipt.detail, "cancel_reason": reason},
            approved_by=receipt.approved_by,
        )
        return self._store(cancelled)

    def undo(self, receipt_id: str, *, actor: str) -> Receipt:
        receipt = self.get(receipt_id)
        if receipt.status != "executed":
            raise ValueError(f"cannot undo a receipt that is {receipt.status}")
        handler = self.undo_handlers.get(receipt.action_name)
        if handler is None:
            raise ValueError(f"no undo handler for {receipt.action_name}")
        try:
            detail = handler(Action(id=receipt.id, verb="act", name=receipt.action_name), {"receipt": receipt.to_dict()}) or {}
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"undo failed: {type(exc).__name__}: {exc}") from exc
        undone = Receipt(
            id=receipt.id,
            decision_id=receipt.decision_id,
            action_name=receipt.action_name,
            status="undone",
            actor=actor,
            detail={**receipt.detail, "undo": detail},
            previous_state=receipt.detail,
            approved_by=receipt.approved_by,
        )
        return self._store(undone)

    def get(self, receipt_id: str) -> Receipt:
        receipt = self.receipts.get(receipt_id)
        if receipt is None:
            raise KeyError(receipt_id)
        return receipt

    def _store(self, receipt: Receipt) -> Receipt:
        self.receipts[receipt.id] = receipt
        return receipt
