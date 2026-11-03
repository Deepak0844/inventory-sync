from app.engine.listing import ListingState, StockStatus
from app.engine.plan import MappedVariant, plan_supplier_run
from app.engine.safety import KillSwitchRules
from app.engine.variant import Action, VariantState

RULES = KillSwitchRules()
IN, OUT, UNK = StockStatus.IN_STOCK, StockStatus.OUT_OF_STOCK, StockStatus.UNKNOWN


def states(status: StockStatus, n: int, quantity: int | None = None) -> dict[str, ListingState]:
    return {f"l{i}": ListingState(status=status, quantity=quantity) for i in range(n)}


def variants(n: int) -> list[MappedVariant]:
    return [MappedVariant(f"v{i}", [f"l{i}"]) for i in range(n)]


def available(n: int) -> dict[str, VariantState | None]:
    return {f"v{i}": VariantState.AVAILABLE for i in range(n)}


def test_a_bad_run_where_every_listing_flips_is_held_and_changes_nothing() -> None:
    plan = plan_supplier_run(states(OUT, 10), variants(10), available(10), 100, 10, RULES)
    assert plan.applied == []
    assert len(plan.held) == 10
    assert {c.decision.action for c in plan.held} == {Action.SELL_OUT}


def test_a_single_sell_out_among_many_listings_is_applied() -> None:
    listings = states(IN, 10, 5)
    listings["l0"] = ListingState(status=OUT)
    plan = plan_supplier_run(listings, variants(10), available(10), 100, 10, RULES)
    sells = [c for c in plan.applied if c.decision.action is Action.SELL_OUT]
    assert [c.variant_id for c in sells] == ["v0"]
    assert plan.held == []


def test_a_restore_alone_is_applied() -> None:
    sold_out: dict[str, VariantState | None] = {"v0": VariantState.SOLD_OUT}
    plan = plan_supplier_run(states(IN, 1), variants(1), sold_out, 100, 1, RULES)
    assert [(c.variant_id, c.decision.action) for c in plan.applied] == [
        ("v0", Action.SET_AVAILABLE)
    ]
    assert plan.held == []


def test_unknown_listings_produce_no_change_at_all() -> None:
    for variant_state in (None, VariantState.AVAILABLE, VariantState.SOLD_OUT):
        plan = plan_supplier_run(states(UNK, 3), variants(3), {f"v{i}": variant_state
                                                               for i in range(3)}, 100, 3, RULES)
        assert (plan.applied, plan.held) == ([], [])


def test_priority_is_the_position_in_the_mapping() -> None:
    listings = {"a": ListingState(status=IN, quantity=4), "b": ListingState(status=IN, quantity=9)}
    mapped = [MappedVariant("v", ["a", "b"])]
    plan = plan_supplier_run(listings, mapped, {"v": VariantState.AVAILABLE}, 100, 2, RULES)
    assert plan.applied[0].decision.quantity == 4


def test_quantity_is_capped_at_the_supplier_maximum() -> None:
    plan = plan_supplier_run(states(IN, 1, 500), variants(1), {"v0": None}, 50, 1, RULES)
    assert plan.applied[0].decision.quantity == 50
