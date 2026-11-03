"""Per-Listing Stock Status transitions (PLAN.md section 7).

A pure function over plain data: no database, network, browser or clock. Not
responsible for scheduling the confirmation reads; the scheduler does that.
"""

from dataclasses import dataclass, replace
from enum import Enum

from app.flows.results import ReadingResult


class StockStatus(Enum):
    """What the system believes about a Listing."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReadingRules:
    """Per-Supplier confirmation rules. Defaults follow PLAN.md."""

    out_confirm_reads: int = 2
    in_confirm_reads: int = 1
    confirm_gap_s: float = 1800.0
    removed_as_unknown: bool = False


@dataclass(frozen=True)
class ListingState:
    """A Listing's status plus the readings still waiting for confirmation."""

    status: StockStatus = StockStatus.UNKNOWN
    removed: bool = False
    last_success_at: float | None = None
    streak_kind: StockStatus | None = None
    streak_count: int = 0
    streak_last_at: float = 0.0


def apply_reading(
    state: ListingState, result: ReadingResult, now: float, rules: ReadingRules
) -> ListingState:
    """Return the new state after one reading taken at `now` (epoch seconds).

    An Unknown reading changes nothing, including a pending confirmation: it
    says nothing about stock, so it can neither confirm nor cancel one. A
    reading that disagrees with the current status only counts toward
    confirmation if it is at least `confirm_gap_s` after the previous counted
    one, so a quick re-run cannot confirm Out of Stock by itself.
    """
    kind = _kind(result, rules)
    if kind is None:
        return state
    state = replace(state, last_success_at=now)
    removed = result is ReadingResult.LISTING_REMOVED
    if kind is state.status:
        return replace(state, removed=removed, streak_kind=None, streak_count=0)

    if state.streak_kind is kind:
        if now - state.streak_last_at < rules.confirm_gap_s:
            return state
        count = state.streak_count + 1
    else:
        count = 1
    needed = rules.out_confirm_reads if kind is StockStatus.OUT_OF_STOCK else rules.in_confirm_reads
    if count >= needed:
        return replace(state, status=kind, removed=removed, streak_kind=None, streak_count=0)
    return replace(state, streak_kind=kind, streak_count=count, streak_last_at=now)


def _kind(result: ReadingResult, rules: ReadingRules) -> StockStatus | None:
    if result is ReadingResult.IN_STOCK:
        return StockStatus.IN_STOCK
    if result is ReadingResult.OUT_OF_STOCK:
        return StockStatus.OUT_OF_STOCK
    if result is ReadingResult.LISTING_REMOVED and not rules.removed_as_unknown:
        return StockStatus.OUT_OF_STOCK
    return None
