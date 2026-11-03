"""Safety rules: the kill switch, the Stale rule and order flags (PLAN.md sections 8-9).

Pure functions over plain data; `now` is always passed in. Not responsible for
storing Pending Approval changes, asking the owner, or reading orders from Shopify.
The system only flags orders; it never cancels them or contacts customers.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.engine.changes import VariantChange
from app.engine.listing import ListingState, StockStatus
from app.engine.variant import Action

HOUR_S = 3600.0


@dataclass(frozen=True)
class KillSwitchRules:
    """Hold Sold Out changes when this many of a Supplier's Listings flip in one run."""

    percent: float = 0.30
    max_flips: int = 20


@dataclass(frozen=True)
class Partition:
    """Changes to apply now, and changes held as Pending Approval."""

    applied: list[VariantChange]
    held: list[VariantChange]


def partition_changes(
    changes: Sequence[VariantChange],
    total_listings: int,
    rules: KillSwitchRules,
    flipped_listings: int | None = None,
) -> Partition:
    """Split one Supplier run's changes into applied and held (Pending Approval).

    Args:
        changes: The decisions for every Variant of the Supplier in this run.
        total_listings: How many Listings the Supplier has. With none, any Sold Out
            change is held.
        rules: The kill switch thresholds.
        flipped_listings: How many Listings flipped to Out of Stock in this run.
            PLAN.md measures the kill switch in Listings, and a Variant can have
            several, so the caller that knows the mapping passes this. Without it,
            each Sold Out change counts as one flip.

    Returns:
        If the Sold Out flips reach `percent` of the Listings, or exceed
        `max_flips`, every Sold Out change is held. Restores are never held, and
        no-change decisions appear in neither list.
    """
    sell_outs = [c for c in changes if c.decision.action is Action.SELL_OUT]
    others = [c for c in changes if c.decision.action is Action.SET_AVAILABLE]
    if not sell_outs:
        return Partition(applied=others, held=[])
    flips = len(sell_outs) if flipped_listings is None else flipped_listings
    # A flip with no known Listings is inconsistent data, so hold it rather than guess.
    tripped = (
        flips > rules.max_flips or total_listings <= 0 or flips / total_listings >= rules.percent
    )
    if tripped:
        return Partition(applied=others, held=sell_outs)
    return Partition(applied=[*sell_outs, *others], held=[])


def is_variant_stale(listings: Sequence[ListingState], now: float, interval_s: float) -> bool:
    """Whether a Variant is Stale.

    Args:
        listings: The Stock State of each Listing mapped to the Variant.
        now: Epoch seconds.
        interval_s: The Supplier's check interval in seconds.

    Returns:
        True for a Variant with no Listings; with no In Stock Listing and any
        Unknown one; or whose last successful check (taken over the In Stock
        Listings, else all of them) is missing or older than twice the interval.
    """
    if not listings:
        return True
    in_stock = [x for x in listings if x.status is StockStatus.IN_STOCK]
    if not in_stock and any(x.status is StockStatus.UNKNOWN for x in listings):
        return True
    relevant = in_stock or list(listings)
    times = [x.last_success_at for x in relevant]
    if any(t is None for t in times):
        return True
    oldest = min(t for t in times if t is not None)
    return now - oldest > 2 * interval_s


class OrderFlagReason(Enum):
    """Why an order is flagged "verify with Supplier"."""

    STALE = "stale"
    RECENTLY_SOLD_OUT = "recently_sold_out"


@dataclass(frozen=True)
class VariantSafety:
    """What order flagging needs to know about one ordered Variant."""

    variant_id: str
    stale: bool
    sold_out_at: float | None


@dataclass(frozen=True)
class OrderFlag:
    """Whether an order should be flagged, and why."""

    flagged: bool
    reasons: tuple[OrderFlagReason, ...]


def flag_order(
    variants: Sequence[VariantSafety], now: float, recently_sold_out_s: float = 6 * HOUR_S
) -> OrderFlag:
    """Flag an order that contains a Stale Variant or one Sold Out recently.

    Args:
        variants: The ordered Variants.
        now: Epoch seconds.
        recently_sold_out_s: How long after going Sold Out a Variant still
            counts as risky (6 hours by default, editable).

    Returns:
        The flag with each reason listed once. Unmapped Variants are the
        caller's concern.
    """
    reasons: list[OrderFlagReason] = []
    if any(v.stale for v in variants):
        reasons.append(OrderFlagReason.STALE)
    if any(v.sold_out_at is not None and now - v.sold_out_at <= recently_sold_out_s
           for v in variants):
        reasons.append(OrderFlagReason.RECENTLY_SOLD_OUT)
    return OrderFlag(flagged=bool(reasons), reasons=tuple(reasons))
