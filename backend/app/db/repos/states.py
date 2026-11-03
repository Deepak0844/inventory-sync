"""Persisted Listing and Variant state for the decision engine.

Not responsible for the transitions themselves (`app.engine`). Converts the
engine's epoch-second floats to and from stored timestamps.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ListingStateRow, VariantStateRow
from app.engine.listing import ListingState, StockStatus


@dataclass(frozen=True)
class VariantStateRecord:
    variant_id: int
    state: str
    sold_out_at: datetime | None
    last_written_quantity: int | None


def _to_state(row: ListingStateRow) -> ListingState:
    return ListingState(
        status=StockStatus(row.status), removed=row.removed,
        last_success_at=None if row.last_success_at is None else row.last_success_at.timestamp(),
        quantity=row.quantity,
        streak_kind=None if row.streak_kind is None else StockStatus(row.streak_kind),
        streak_count=row.streak_count, streak_last_at=row.streak_last_at,
    )


class StateRepo:
    """Listing and Variant state rows."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_listing_state(self, listing_id: int) -> ListingState:
        """Return the Listing's state; a Listing never read is Unknown."""
        row = self._s.get(ListingStateRow, listing_id)
        return ListingState() if row is None else _to_state(row)

    def listing_states(self, listing_ids: Collection[int] | None = None) -> dict[int, ListingState]:
        """Return the state of many Listings in one query (all of them when None).

        A Listing missing from the result has never been read, so it is Unknown.
        """
        query = select(ListingStateRow)
        if listing_ids is not None:
            if not listing_ids:
                return {}
            query = query.where(ListingStateRow.listing_id.in_(listing_ids))
        return {row.listing_id: _to_state(row) for row in self._s.scalars(query)}

    def save_listing_state(self, listing_id: int, state: ListingState) -> None:
        """Insert or replace the Listing's state."""
        self._s.merge(ListingStateRow(
            listing_id=listing_id, status=state.status.value, removed=state.removed,
            quantity=state.quantity,
            last_success_at=None if state.last_success_at is None
            else datetime.fromtimestamp(state.last_success_at, UTC),
            streak_kind=None if state.streak_kind is None else state.streak_kind.value,
            streak_count=state.streak_count, streak_last_at=state.streak_last_at,
        ))
        self._s.commit()

    def get_variant_state(self, variant_id: int) -> VariantStateRecord | None:
        """Return what was last set in Shopify, or None if the Variant is not managed yet."""
        row = self._s.get(VariantStateRow, variant_id)
        if row is None:
            return None
        return VariantStateRecord(variant_id, row.state, row.sold_out_at,
                                  row.last_written_quantity)

    def save_variant_state(
        self, variant_id: int, state: str, now: datetime, quantity: int | None
    ) -> None:
        """Record a write to Shopify. `sold_out_at` keeps the time the Variant first sold out."""
        row = self._s.get(VariantStateRow, variant_id)
        kept = row.sold_out_at if row is not None and row.state == "sold_out" else None
        sold_out_at = (kept or now) if state == "sold_out" else None
        self._s.merge(VariantStateRow(variant_id=variant_id, state=state, sold_out_at=sold_out_at,
                                      last_written_quantity=quantity, updated_at=now))
        self._s.commit()
