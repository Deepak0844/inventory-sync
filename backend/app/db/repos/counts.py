"""Cheap COUNT queries for the shell banner and the Overview.

The banner is polled on every screen, so it must not load whole lists just to
take their length. Not responsible for the lists themselves (the other repos).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Approval, FlaggedOrder, Notification, VariantStateRow


class Counts:
    """Row counts, each one query."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def pending_approvals(self) -> int:
        """Batches still waiting for the owner."""
        return self._s.scalar(select(func.count()).where(Approval.state == "pending")) or 0

    def flagged_orders(self) -> int:
        """Orders flagged "verify with Supplier"."""
        return self._s.scalar(select(func.count()).select_from(FlaggedOrder)) or 0

    def unresolved_notifications(self) -> int:
        """Notifications not yet resolved."""
        return self._s.scalar(
            select(func.count()).where(Notification.resolved_at.is_(None))) or 0

    def variants_by_state(self) -> dict[str, int]:
        """How many Variants are in each managed state (a Variant never written has none)."""
        rows = self._s.execute(
            select(VariantStateRow.state, func.count()).group_by(VariantStateRow.state)).all()
        return {state: n for state, n in rows}
