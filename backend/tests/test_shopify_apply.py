import pytest

from app.engine.changes import VariantChange
from app.engine.variant import Action, Decision, Reason
from app.shopify.apply import apply_changes
from app.shopify.client import ShopifyError


class FakeWriter:
    def __init__(self, failing: set[str] | None = None, crash: set[str] | None = None) -> None:
        self.writes: list[tuple[str, int]] = []
        self.failing = failing or set()
        self.crash = crash or set()

    def set_available(self, variant_id: str, quantity: int) -> None:
        if variant_id in self.crash:
            raise RuntimeError("bug")
        if variant_id in self.failing:
            raise ShopifyError(f"{variant_id} rejected")
        self.writes.append((variant_id, quantity))


def sell_out(variant_id: str) -> VariantChange:
    return VariantChange(variant_id, Decision(Action.SELL_OUT, 0, Reason.ALL_OUT_OF_STOCK))


def restore(variant_id: str, quantity: int = 100) -> VariantChange:
    return VariantChange(variant_id, Decision(Action.SET_AVAILABLE, quantity, Reason.RESTORE))


def nothing(variant_id: str) -> VariantChange:
    return VariantChange(variant_id, Decision(Action.NONE))


def test_sell_out_writes_zero_and_set_available_writes_the_quantity() -> None:
    writer = FakeWriter()
    report = apply_changes([sell_out("a"), restore("b", 7)], writer)
    assert writer.writes == [("a", 0), ("b", 7)]
    assert [c.variant_id for c in report.applied] == ["a", "b"]
    assert report.failed == []


def test_changes_with_no_action_never_reach_shopify() -> None:
    writer = FakeWriter()
    report = apply_changes([nothing("a"), nothing("b")], writer)
    assert writer.writes == []
    assert report.applied == [] and report.failed == []


def test_one_rejected_variant_does_not_stop_the_others() -> None:
    writer = FakeWriter(failing={"b"})
    report = apply_changes([sell_out("a"), sell_out("b"), sell_out("c")], writer)
    assert writer.writes == [("a", 0), ("c", 0)]
    assert [c.variant_id for c in report.applied] == ["a", "c"]
    assert [(f.change.variant_id, f.error) for f in report.failed] == [("b", "b rejected")]


def test_errors_other_than_shopify_errors_are_not_swallowed() -> None:
    with pytest.raises(RuntimeError):
        apply_changes([sell_out("a")], FakeWriter(crash={"a"}))


@pytest.mark.parametrize("action", [Action.SELL_OUT, Action.SET_AVAILABLE])
def test_a_change_with_an_action_but_no_quantity_is_reported_not_dropped(action: Action) -> None:
    writer = FakeWriter()
    broken = VariantChange("a", Decision(action, None, Reason.RESTORE))
    report = apply_changes([broken, sell_out("b")], writer)
    assert writer.writes == [("b", 0)]
    assert [(f.change.variant_id, f.error) for f in report.failed] == [
        ("a", "decision has no quantity")
    ]
    assert [c.variant_id for c in report.applied] == ["b"]
