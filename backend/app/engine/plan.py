"""Turning a Supplier's Listing states into the changes to apply or hold.

Pure function. Not responsible for loading states from the database or for
writing to Shopify.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.engine.listing import ListingState
from app.engine.safety import KillSwitchRules, VariantChange, partition_changes
from app.engine.variant import ListingView, VariantState, decide_variant


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
        The plan. Unknown Listings produce no change.

    Raises:
        KeyError: if a mapping names a Listing or Variant with no state entry.
        InvalidMaxQuantity: if `max_quantity` is below 1 and a quantity is needed.
    """
    changes: list[VariantChange] = []
    for variant in variants:
        views = [
            ListingView(
                status=listing_states[lid].status,
                priority=index,
                quantity=listing_states[lid].quantity,
            )
            for index, lid in enumerate(variant.listing_ids_by_priority)
        ]
        decision = decide_variant(views, states[variant.variant_id], max_quantity)
        changes.append(VariantChange(variant.variant_id, decision))
    partition = partition_changes(changes, total_listings, rules)
    return RunPlan(applied=partition.applied, held=partition.held)
