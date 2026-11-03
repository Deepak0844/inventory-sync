"""Per-Variant decision from its Listings (PLAN.md sections 7 and 8).

Pure functions over plain data. Not responsible for the kill switch (Phase 4)
or for writing to Shopify.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.engine.listing import StockStatus

DEFAULT_QUANTITY = 100


class VariantState(Enum):
    """What the system last set a Variant to in Shopify. None means not managed yet."""

    AVAILABLE = "available"
    SOLD_OUT = "sold_out"


class Action(Enum):
    """What to do in Shopify."""

    NONE = "none"
    SELL_OUT = "sell_out"
    SET_AVAILABLE = "set_available"


class Reason(Enum):
    """Why an action was chosen, kept in the change history."""

    ALL_OUT_OF_STOCK = "all_out_of_stock"
    RESTORE = "restore"
    REFRESH = "refresh"
    FIRST_SYNC = "first_sync"


@dataclass(frozen=True)
class ListingView:
    """A mapped Listing as the decision sees it. Lower `priority` wins."""

    status: StockStatus
    priority: int
    quantity: int | None = None


@dataclass(frozen=True)
class Decision:
    """The result for one Variant."""

    action: Action
    quantity: int | None = None
    reason: Reason | None = None


NO_CHANGE = Decision(Action.NONE)


def quantity_to_write(supplier_quantity: int | None, max_quantity: int) -> int:
    """Return the quantity to set: the Supplier's, else 100, never above `max_quantity`.

    A quantity of zero on a Listing that is In Stock contradicts itself, so it
    is treated as "not shown" rather than writing 0 and hiding an item the
    Supplier says it has.
    """
    base = supplier_quantity if supplier_quantity and supplier_quantity > 0 else DEFAULT_QUANTITY
    return min(base, max_quantity)


def decide_variant(
    listings: Sequence[ListingView], state: VariantState | None, max_quantity: int
) -> Decision:
    """Decide what to do for a Variant. Sold Out only when every Listing is Out of Stock.

    Any Unknown Listing that is not outweighed by an In Stock one means no change.
    """
    in_stock = sorted((v for v in listings if v.status is StockStatus.IN_STOCK),
                      key=lambda v: v.priority)
    if in_stock:
        if state is None:
            reason = Reason.FIRST_SYNC
        elif state is VariantState.SOLD_OUT:
            reason = Reason.RESTORE
        else:
            reason = Reason.REFRESH
        quantity = quantity_to_write(in_stock[0].quantity, max_quantity)
        return Decision(Action.SET_AVAILABLE, quantity, reason)
    if listings and all(v.status is StockStatus.OUT_OF_STOCK for v in listings):
        if state is VariantState.SOLD_OUT:
            return NO_CHANGE
        return Decision(Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK)
    return NO_CHANGE
