"""Turning a Supplier's Listing states into the changes to apply or hold.

Pure function. Not responsible for loading states from the database or for
writing to Shopify.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.engine.changes import VariantChange
from app.engine.listing import ListingState
from app.engine.safety import KillSwitchRules, partition_changes
from app.engine.variant import Action, ListingView, VariantState, decide_variant


@dataclass(frozen=True)
class MappedVariant:
    """A Variant and its Listing ids, highest priority first."""

    variant_id: str
    listing_ids_by_priority: Sequence[str]


@dataclass(frozen=True)
class RunPlan:
    """The outcome of one Supplier run: apply these, hold those as Pending Approval."""

    applied: list[VariantChange]
    held: list[VariantChange]


def plan_supplier_run(
    listing_states: Mapping[str, ListingState],
    variants: Sequence[MappedVariant],
    states: Mapping[str, VariantState | None],
    max_quantity: int,
    total_listings: int,
    rules: KillSwitchRules,
) -> RunPlan:
    """Decide every Variant of a Supplier and apply the kill switch.

    Args:
        listing_states: Each Listing's state, by Listing id.
        variants: The mapped Variants; priority is the position in the list.
        states: What the system last set per Variant id (None = not managed yet).
        max_quantity: The Supplier's quantity cap.
        total_listings: The Supplier's total Listing count, for the kill switch.
        rules: The kill switch thresholds.

    Returns:
        The plan. A Listing with no state entry has never been read, so it is
        Unknown and produces no change. A Variant with no entry in `states` is
        not managed yet. The kill switch counts the Listings of the Variants
        that sell out, not the Variants.

    Raises:
        InvalidMaxQuantity: if `max_quantity` is below 1 and a quantity is needed.
    """
    changes: list[VariantChange] = []
    flipped: set[str] = set()
    for variant in variants:
        views = []
        for index, lid in enumerate(variant.listing_ids_by_priority):
            state = listing_states.get(lid, ListingState())
            views.append(ListingView(state.status, index, state.quantity))
        decision = decide_variant(views, states.get(variant.variant_id), max_quantity)
        changes.append(VariantChange(variant.variant_id, decision))
        if decision.action is Action.SELL_OUT:
            flipped.update(variant.listing_ids_by_priority)
    partition = partition_changes(changes, total_listings, rules, len(flipped))
    return RunPlan(applied=partition.applied, held=partition.held)
