"""Readings and the inventory change history.

Not responsible for pruning old readings or screenshots (a later job).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InventoryChange, Reading, Variant


@dataclass(frozen=True)
class ReadingRecord:
    result: str
    error_kind: str | None
    quantity: int | None
    read_at: datetime
    screenshot_path: str | None


@dataclass(frozen=True)
class ChangeRecord:
    at: datetime
    variant_id: int
    sku: str
    from_state: str | None
    to_state: str
    reason: str
    approval: str


class HistoryRepo:
    """Append-only readings and changes."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def add_reading(
        self, listing_id: int, result: str, error_kind: str | None, quantity: int | None,
        read_at: datetime, screenshot_path: str | None = None,
    ) -> None:
        """Record one reading of a Listing."""
        self._s.add(Reading(listing_id=listing_id, result=result, error_kind=error_kind,
                            quantity=quantity, read_at=read_at, screenshot_path=screenshot_path))
        self._s.commit()

    def recent_readings(self, listing_id: int, n: int) -> list[ReadingRecord]:
        """Return the last `n` readings, newest first."""
        rows = self._s.scalars(select(Reading).where(Reading.listing_id == listing_id)
                               .order_by(Reading.read_at.desc(), Reading.id.desc()).limit(n))
        return [ReadingRecord(r.result, r.error_kind, r.quantity, r.read_at, r.screenshot_path)
                for r in rows]

    def record_change(
        self, variant_id: int, from_state: str | None, to_state: str, reason: str,
        approval: str, at: datetime, supplier_id: int | None = None,
    ) -> None:
        """Record a state change written to Shopify, and why."""
        self._s.add(InventoryChange(variant_id=variant_id, supplier_id=supplier_id,
                                    from_state=from_state, to_state=to_state, reason=reason,
                                    approval=approval, at=at))
        self._s.commit()

    def all_changes(self) -> list[ChangeRecord]:
        """Return every change, oldest first (for the daily Sold Out history)."""
        rows = self._s.execute(
            select(InventoryChange, Variant.sku)
            .join(Variant, Variant.id == InventoryChange.variant_id)
            .order_by(InventoryChange.at, InventoryChange.id)
        ).all()
        return [ChangeRecord(c.at, c.variant_id, sku, c.from_state, c.to_state, c.reason,
                             c.approval) for c, sku in rows]

    def recent_changes(self, limit: int) -> list[ChangeRecord]:
        """Return the latest changes, newest first."""
        rows = self._s.execute(
            select(InventoryChange, Variant.sku)
            .join(Variant, Variant.id == InventoryChange.variant_id)
            .order_by(InventoryChange.at.desc(), InventoryChange.id.desc()).limit(limit)
        ).all()
        return [ChangeRecord(c.at, c.variant_id, sku, c.from_state, c.to_state, c.reason,
                             c.approval) for c, sku in rows]
