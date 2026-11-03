from app.engine.listing import ListingState, StockStatus
from app.engine.safety import (
    KillSwitchRules,
    OrderFlagReason,
    VariantChange,
    VariantSafety,
    flag_order,
    is_variant_stale,
    partition_changes,
)
from app.engine.variant import Action, Decision, Reason

RULES = KillSwitchRules(percent=0.30, max_flips=20)
SELL = Decision(Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK)
RESTORE = Decision(Action.SET_AVAILABLE, 100, Reason.RESTORE)
NOTHING = Decision(Action.NONE)


def sells(n: int) -> list[VariantChange]:
    return [VariantChange(f"v{i}", SELL) for i in range(n)]


def test_empty_run_changes_nothing() -> None:
    p = partition_changes([], 10, RULES)
    assert (p.applied, p.held) == ([], [])


def test_below_thirty_percent_applies_the_sell_outs() -> None:
    p = partition_changes(sells(2), 10, RULES)
    assert len(p.applied) == 2 and p.held == []


def test_exactly_thirty_percent_trips_the_kill_switch() -> None:
    p = partition_changes(sells(3), 10, RULES)
    assert p.applied == [] and len(p.held) == 3


def test_just_under_thirty_percent_does_not_trip() -> None:
    p = partition_changes(sells(20), 69, RULES)  # 29.0%, and not over the 20-flip limit
    assert len(p.applied) == 20 and p.held == []


def test_twenty_flips_do_not_trip_but_twenty_one_do() -> None:
    assert partition_changes(sells(20), 1000, RULES).held == []
    assert len(partition_changes(sells(21), 1000, RULES).held) == 21


def test_restores_are_never_held_even_when_tripped() -> None:
    changes = [*sells(5), VariantChange("r", RESTORE)]
    p = partition_changes(changes, 10, RULES)
    assert [c.variant_id for c in p.applied] == ["r"]
    assert len(p.held) == 5


def test_no_change_decisions_are_dropped() -> None:
    p = partition_changes([VariantChange("n", NOTHING)], 10, RULES)
    assert (p.applied, p.held) == ([], [])


def test_zero_total_listings_holds_the_flip_without_dividing_by_zero() -> None:
    p = partition_changes(sells(1), 0, RULES)
    assert len(p.held) == 1


def listing(status: StockStatus, success: float | None) -> ListingState:
    return ListingState(status=status, last_success_at=success)


IN, OUT, UNK = StockStatus.IN_STOCK, StockStatus.OUT_OF_STOCK, StockStatus.UNKNOWN


def test_variant_with_no_listings_is_stale() -> None:
    assert is_variant_stale([], 0.0, 3600.0)


def test_fresh_in_stock_variant_is_not_stale() -> None:
    assert not is_variant_stale([listing(IN, 1000.0)], 2000.0, 3600.0)


def test_check_older_than_twice_the_interval_is_stale() -> None:
    assert is_variant_stale([listing(IN, 0.0)], 7201.0, 3600.0)
    assert not is_variant_stale([listing(IN, 0.0)], 7200.0, 3600.0)


def test_never_checked_listing_is_stale() -> None:
    assert is_variant_stale([listing(IN, None)], 10.0, 3600.0)


def test_unknown_listing_without_an_in_stock_one_is_stale() -> None:
    assert is_variant_stale([listing(OUT, 1000.0), listing(UNK, 1000.0)], 2000.0, 3600.0)


def test_unknown_listing_is_outweighed_by_a_fresh_in_stock_one() -> None:
    assert not is_variant_stale([listing(UNK, None), listing(IN, 1000.0)], 2000.0, 3600.0)


def test_only_in_stock_listings_set_the_age_when_one_is_in_stock() -> None:
    old_out = listing(OUT, 0.0)
    assert not is_variant_stale([old_out, listing(IN, 9000.0)], 10000.0, 3600.0)


def test_all_out_of_stock_uses_the_oldest_check() -> None:
    assert is_variant_stale([listing(OUT, 9000.0), listing(OUT, 0.0)], 10000.0, 3600.0)


def test_order_with_a_stale_variant_is_flagged() -> None:
    flag = flag_order([VariantSafety("a", stale=True, sold_out_at=None)], 100.0)
    assert flag.flagged and flag.reasons == (OrderFlagReason.STALE,)


def test_order_with_a_recently_sold_out_variant_is_flagged() -> None:
    flag = flag_order([VariantSafety("a", stale=False, sold_out_at=100.0)], 100.0 + 6 * 3600)
    assert flag.flagged and flag.reasons == (OrderFlagReason.RECENTLY_SOLD_OUT,)


def test_variant_sold_out_long_ago_is_not_flagged() -> None:
    flag = flag_order([VariantSafety("a", stale=False, sold_out_at=0.0)], 6 * 3600 + 1)
    assert not flag.flagged and flag.reasons == ()


def test_window_is_editable() -> None:
    v = [VariantSafety("a", stale=False, sold_out_at=0.0)]
    assert flag_order(v, 7200.0, recently_sold_out_s=3 * 3600).flagged
    assert not flag_order(v, 7200.0, recently_sold_out_s=3600).flagged


def test_healthy_order_is_not_flagged() -> None:
    assert not flag_order([VariantSafety("a", stale=False, sold_out_at=None)], 0.0).flagged


def test_each_reason_is_listed_once() -> None:
    v = [VariantSafety("a", True, 10.0), VariantSafety("b", True, 10.0)]
    assert flag_order(v, 20.0).reasons == (OrderFlagReason.STALE, OrderFlagReason.RECENTLY_SOLD_OUT)
