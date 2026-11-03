"""Pending Approval batches held by the kill switch.

Not responsible for writing approved changes to Shopify; the caller does that
with what `decide` returns.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Approval, ApprovalChange, Supplier, Variant


@dataclass(frozen=True)
class HeldChange:
    variant_id: int
    from_state: str | None
    to_state: str
    quantity: int


@dataclass(frozen=True)
class ApprovalChangeRecord:
    variant_id: int
    sku: str
    from_state: str | None
    to_state: str
    quantity: int


@dataclass(frozen=True)
class PendingApproval:
    id: int
    supplier_id: int
    supplier_name: str
    created_at: datetime
    changes: list[ApprovalChangeRecord]


class ApprovalRepo:
    """Rows of `approvals` and `approval_changes`."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, supplier_id: int, changes: list[HeldChange], now: datetime) -> int:
        """Hold a batch of changes for the owner. Returns the approval id."""
        approval = Approval(supplier_id=supplier_id, created_at=now)
        self._s.add(approval)
        self._s.flush()
        self._s.add_all(ApprovalChange(approval_id=approval.id, variant_id=c.variant_id,
                                       from_state=c.from_state, to_state=c.to_state,
                                       quantity=c.quantity) for c in changes)
        self._s.commit()
        return approval.id

    def merge_changes(self, approval_id: int, changes: list[HeldChange]) -> None:
        """Add changes to a pending batch; a Variant already in it is updated, not repeated."""
        existing = {c.variant_id: c for c in self._s.scalars(
            select(ApprovalChange).where(ApprovalChange.approval_id == approval_id))}
        for c in changes:
            row = existing.get(c.variant_id)
            if row is None:
                self._s.add(ApprovalChange(approval_id=approval_id, variant_id=c.variant_id,
                                           from_state=c.from_state, to_state=c.to_state,
                                           quantity=c.quantity))
            else:
                row.from_state, row.to_state, row.quantity = c.from_state, c.to_state, c.quantity
        self._s.commit()

    def list_pending(self) -> list[PendingApproval]:
        """Return batches still waiting, oldest first."""
        rows = self._s.execute(
            select(Approval, Supplier.name).join(Supplier, Supplier.id == Approval.supplier_id)
            .where(Approval.state == "pending").order_by(Approval.created_at, Approval.id)
        ).all()
        return [PendingApproval(a.id, a.supplier_id, name, a.created_at, self._changes(a.id))
                for a, name in rows]

    def decide(
        self, approval_id: int, approved: bool, now: datetime
    ) -> list[ApprovalChangeRecord] | None:
        """Approve or reject a pending batch, once.

        Returns the changes to apply when approved, an empty list when
        rejected, and None if the batch is unknown or already decided, so a
        double click can never apply the same changes twice.
        """
        result = self._s.execute(
            update(Approval).where(Approval.id == approval_id, Approval.state == "pending")
            .values(state="approved" if approved else "rejected", decided_at=now)
        )
        self._s.commit()
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return None
        return self._changes(approval_id) if approved else []

    def _changes(self, approval_id: int) -> list[ApprovalChangeRecord]:
        rows = self._s.execute(
            select(ApprovalChange, Variant.sku)
            .join(Variant, Variant.id == ApprovalChange.variant_id)
            .where(ApprovalChange.approval_id == approval_id).order_by(ApprovalChange.id)
        ).all()
        return [ApprovalChangeRecord(c.variant_id, sku, c.from_state, c.to_state, c.quantity)
                for c, sku in rows]
