from app.engine.listing import StockStatus
from app.engine.variant import (
    Action,
    ListingView,
    Reason,
    VariantState,
    decide_variant,
    quantity_to_write,
)

IN, OUT, UNK = StockStatus.IN_STOCK, StockStatus.OUT_OF_STOCK, StockStatus.UNKNOWN


def view(status: StockStatus, priority: int = 1, quantity: int | None = None) -> ListingView:
    return ListingView(status=status, priority=priority, quantity=quantity)


def decide(listings: list[ListingView], state: VariantState | None = VariantState.AVAILABLE,
           max_quantity: int = 100) -> tuple[Action, int | None, Reason | None]:
    d = decide_variant(listings, state, max_quantity)
    return d.action, d.quantity, d.reason


def test_all_listings_out_of_stock_sells_the_variant_out() -> None:
    assert decide([view(OUT), view(OUT, 2)]) == (Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK)


def test_already_sold_out_variant_is_left_alone() -> None:
    assert decide([view(OUT)], VariantState.SOLD_OUT) == (Action.NONE, None, None)


def test_one_listing_in_stock_keeps_the_variant_available() -> None:
    d = decide([view(OUT), view(IN, 2)], VariantState.AVAILABLE)
    assert d[0] is Action.SET_AVAILABLE
    assert d[2] is Reason.REFRESH


def test_in_stock_listing_restores_a_sold_out_variant() -> None:
    action, quantity, reason = decide([view(IN)], VariantState.SOLD_OUT)
    assert (action, quantity, reason) == (Action.SET_AVAILABLE, 100, Reason.RESTORE)


def test_a_variant_not_yet_managed_gets_tracking_and_a_quantity() -> None:
    assert decide([view(IN)], None) == (Action.SET_AVAILABLE, 100, Reason.FIRST_SYNC)


def test_unknown_listing_among_out_of_stock_changes_nothing() -> None:
    assert decide([view(OUT), view(UNK, 2)]) == (Action.NONE, None, None)


def test_only_unknown_listings_change_nothing_whatever_the_state() -> None:
    for state in (None, VariantState.AVAILABLE, VariantState.SOLD_OUT):
        assert decide([view(UNK)], state) == (Action.NONE, None, None)


def test_in_stock_beats_an_unknown_listing() -> None:
    assert decide([view(UNK), view(IN, 2)], VariantState.SOLD_OUT)[0] is Action.SET_AVAILABLE


def test_a_variant_with_no_listings_changes_nothing() -> None:
    assert decide([]) == (Action.NONE, None, None)


def test_quantity_comes_from_the_highest_priority_in_stock_listing() -> None:
    listings = [view(IN, priority=2, quantity=9), view(IN, priority=1, quantity=4)]
    assert decide(listings)[1] == 4


def test_quantity_skips_a_higher_priority_listing_that_is_not_in_stock() -> None:
    listings = [view(OUT, priority=1, quantity=0), view(IN, priority=2, quantity=9)]
    assert decide(listings)[1] == 9


def test_supplier_quantity_is_capped() -> None:
    assert quantity_to_write(500, max_quantity=50) == 50


def test_supplier_quantity_below_the_cap_is_used() -> None:
    assert quantity_to_write(7, max_quantity=50) == 7


def test_default_quantity_is_100_when_the_supplier_shows_none() -> None:
    assert quantity_to_write(None, max_quantity=200) == 100


def test_default_quantity_is_also_capped() -> None:
    assert quantity_to_write(None, max_quantity=30) == 30


def test_zero_quantity_from_an_in_stock_listing_is_not_written_as_available() -> None:
    assert decide([view(IN, quantity=0)])[1] == 100
