import pytest

from app.engine.listing import ListingState, ReadingRules, StockStatus, apply_reading
from app.flows.results import ReadingResult

RULES = ReadingRules(out_confirm_reads=2, in_confirm_reads=1, confirm_gap_s=1800)
START = ListingState()
IN, OUT, UNK = ReadingResult.IN_STOCK, ReadingResult.OUT_OF_STOCK, ReadingResult.UNKNOWN
GONE = ReadingResult.LISTING_REMOVED


def feed(*reads: tuple[ReadingResult, float], rules: ReadingRules = RULES,
         state: ListingState = START) -> ListingState:
    for result, at in reads:
        state = apply_reading(state, result, at, rules)
    return state


def test_a_new_listing_is_unknown() -> None:
    assert START.status is StockStatus.UNKNOWN


def test_unknown_to_in_stock_after_one_reading() -> None:
    assert feed((IN, 0)).status is StockStatus.IN_STOCK


def test_one_out_of_stock_reading_changes_nothing() -> None:
    assert feed((IN, 0), (OUT, 100)).status is StockStatus.IN_STOCK


def test_two_out_of_stock_readings_apart_confirm_out_of_stock() -> None:
    assert feed((IN, 0), (OUT, 100), (OUT, 1900)).status is StockStatus.OUT_OF_STOCK


def test_unknown_to_out_of_stock_needs_two_readings_too() -> None:
    assert feed((OUT, 0)).status is StockStatus.UNKNOWN
    assert feed((OUT, 0), (OUT, 1800)).status is StockStatus.OUT_OF_STOCK


def test_out_of_stock_readings_too_close_together_do_not_confirm() -> None:
    state = feed((IN, 0), (OUT, 100), (OUT, 200))
    assert state.status is StockStatus.IN_STOCK


def test_a_close_reading_does_not_move_the_confirmation_clock() -> None:
    state = feed((IN, 0), (OUT, 100), (OUT, 200), (OUT, 1900))
    assert state.status is StockStatus.OUT_OF_STOCK


def test_in_stock_reading_resets_a_pending_out_of_stock() -> None:
    state = feed((IN, 0), (OUT, 100), (IN, 200), (OUT, 2000))
    assert state.status is StockStatus.IN_STOCK


def test_out_of_stock_to_in_stock_after_one_reading() -> None:
    state = feed((OUT, 0), (OUT, 1800), (IN, 2000))
    assert state.status is StockStatus.IN_STOCK


@pytest.mark.parametrize("start", [IN, OUT])
def test_unknown_reading_changes_nothing(start: ReadingResult) -> None:
    base = feed((start, 0), (start, 1800)) if start is OUT else feed((IN, 0))
    assert feed((UNK, 5000), state=base) == base


def test_unknown_between_two_out_of_stock_readings_does_not_reset_or_confirm() -> None:
    state = feed((IN, 0), (OUT, 100), (UNK, 1000))
    assert state.status is StockStatus.IN_STOCK
    assert feed((OUT, 1900), state=state).status is StockStatus.OUT_OF_STOCK


def test_unknown_reading_never_confirms_out_of_stock() -> None:
    assert feed((IN, 0), (OUT, 100), (UNK, 2000)).status is StockStatus.IN_STOCK


def test_rules_are_editable_per_supplier() -> None:
    quick = ReadingRules(out_confirm_reads=1, in_confirm_reads=1, confirm_gap_s=0)
    assert feed((IN, 0), (OUT, 1), rules=quick).status is StockStatus.OUT_OF_STOCK
    slow = ReadingRules(out_confirm_reads=3, in_confirm_reads=2, confirm_gap_s=60)
    assert feed((IN, 0)).status is StockStatus.IN_STOCK
    assert feed((IN, 0), rules=slow).status is StockStatus.UNKNOWN
    assert feed((IN, 0), (IN, 60), rules=slow).status is StockStatus.IN_STOCK


def test_listing_removed_counts_as_out_of_stock_after_confirmation() -> None:
    state = feed((IN, 0), (GONE, 100))
    assert state.status is StockStatus.IN_STOCK
    state = feed((GONE, 1900), state=state)
    assert state.status is StockStatus.OUT_OF_STOCK
    assert state.removed


def test_listing_removed_can_be_treated_as_unknown_for_a_supplier() -> None:
    rules = ReadingRules(out_confirm_reads=2, in_confirm_reads=1, confirm_gap_s=1800,
                         removed_as_unknown=True)
    state = feed((IN, 0), (GONE, 100), (GONE, 1900), rules=rules)
    assert state.status is StockStatus.IN_STOCK
    assert state.removed  # still flagged for review, only the status is left alone


def test_removed_page_is_a_successful_check_even_when_treated_as_unknown() -> None:
    rules = ReadingRules(removed_as_unknown=True)
    assert feed((IN, 0), (GONE, 500), rules=rules).last_success_at == 500


def test_removed_flag_clears_when_the_listing_is_in_stock_again() -> None:
    state = feed((GONE, 0), (GONE, 1800), (IN, 2000))
    assert state.status is StockStatus.IN_STOCK
    assert not state.removed


def test_last_success_time_moves_on_every_known_reading_but_not_on_unknown() -> None:
    state = feed((IN, 10), (UNK, 20))
    assert state.last_success_at == 10
    assert feed((OUT, 30), state=state).last_success_at == 30


def test_quantity_follows_the_latest_in_stock_reading() -> None:
    state = apply_reading(START, IN, 0, RULES, quantity=7)
    assert state.quantity == 7
    assert apply_reading(state, IN, 10, RULES, quantity=5).quantity == 5


def test_quantity_is_cleared_when_out_of_stock_is_confirmed() -> None:
    state = apply_reading(START, IN, 0, RULES, quantity=7)
    state = feed((OUT, 100), (OUT, 1900), state=state)
    assert state.status is StockStatus.OUT_OF_STOCK
    assert state.quantity is None


def test_quantity_survives_an_unconfirmed_out_of_stock_reading() -> None:
    state = apply_reading(START, IN, 0, RULES, quantity=7)
    assert feed((OUT, 100), state=state).quantity == 7
