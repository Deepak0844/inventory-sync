from app.engine.listing import ListingState, StockStatus
from app.engine.plan import MappedVariant, plan_supplier_run
from app.engine.safety import KillSwitchRules
from app.engine.variant import Action, VariantState
from app.shopify.apply import apply_changes

RULES = KillSwitchRules()
OUT = ListingState(status=StockStatus.OUT_OF_STOCK, last_success_at=1.0)
IN = ListingState(status=StockStatus.IN_STOCK, last_success_at=1.0, quantity=5)


class FakeWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[str, int]] = []

    def set_available(self, variant_id: str, quantity: int) -> None:
        self.writes.append((variant_id, quantity))


def test_a_plan_can_be_applied_directly() -> None:
    plan = plan_supplier_run(
        {"l1": IN}, [MappedVariant("v1", ["l1"])], {"v1": VariantState.SOLD_OUT},
        max_quantity=100, total_listings=1, rules=RULES,
    )
    writer = FakeWriter()
    report = apply_changes(plan.applied, writer)
    assert writer.writes == [("v1", 5)]
    assert len(report.applied) == 1


def test_a_listing_with_no_state_is_unknown_and_changes_nothing() -> None:
    plan = plan_supplier_run(
        {}, [MappedVariant("v1", ["never-checked"])], {"v1": VariantState.AVAILABLE},
        max_quantity=100, total_listings=1, rules=RULES,
    )
    assert plan.applied == [] and plan.held == []


def test_a_variant_with_no_state_entry_is_not_managed_yet() -> None:
    plan = plan_supplier_run(
        {"l1": IN}, [MappedVariant("v1", ["l1"])], {},
        max_quantity=100, total_listings=1, rules=RULES,
    )
    assert plan.applied[0].decision.action is Action.SET_AVAILABLE


def test_kill_switch_counts_listings_that_flipped_not_variants() -> None:
    # 10 Variants with 3 Listings each (30 Listings). 8 Variants sell out: 24 Listings
    # flipped (80%), although only 8 of 30 would be 27% if Variants were counted.
    listing_states = {f"l{v}-{i}": OUT for v in range(10) for i in range(3)}
    variants = [MappedVariant(f"v{v}", [f"l{v}-{i}" for i in range(3)]) for v in range(8)]
    variants += [MappedVariant(f"v{v}", [f"l{v}-{i}" for i in range(3)]) for v in (8, 9)]
    listing_states |= {f"l{v}-0": IN for v in (8, 9)}
    states: dict[str, VariantState | None] = {f"v{v}": VariantState.AVAILABLE for v in range(10)}
    plan = plan_supplier_run(listing_states, variants, states, max_quantity=100,
                             total_listings=30, rules=RULES)
    assert [c.variant_id for c in plan.held] == [f"v{v}" for v in range(8)]
    assert all(c.decision.action is not Action.SELL_OUT for c in plan.applied)
