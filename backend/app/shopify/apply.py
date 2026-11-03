"""Applying decided changes to Shopify, one Variant at a time.

Not responsible for deciding changes or holding them for approval; callers pass
in only what is cleared to be written.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.engine.changes import VariantChange
from app.engine.variant import Action
from app.shopify.client import InventoryWriter, ShopifyError


@dataclass(frozen=True)
class FailedChange:
    """A change Shopify rejected, with the reason."""

    change: VariantChange
    error: str


@dataclass
class ApplyReport:
    """What happened to each change."""

    applied: list[VariantChange] = field(default_factory=list)
    failed: list[FailedChange] = field(default_factory=list)


def apply_changes(changes: Sequence[VariantChange], writer: InventoryWriter) -> ApplyReport:
    """Write each change to Shopify, carrying on past a Variant Shopify rejects.

    Args:
        changes: Cleared changes. Those with no action are skipped and appear in
            neither list, so an Unknown or unchanged Variant never reaches Shopify.
        writer: The Shopify inventory writer.

    Returns:
        Which changes were applied and which failed (to retry and notify).

    Raises:
        Exception: anything other than ShopifyError propagates. It means a bug,
            and silently continuing could hide it.
    """
    report = ApplyReport()
    for change in changes:
        decision = change.decision
        if decision.action is Action.NONE or decision.quantity is None:
            continue
        try:
            writer.set_available(change.variant_id, decision.quantity)
        except ShopifyError as exc:
            report.failed.append(FailedChange(change, str(exc)))
        else:
            report.applied.append(change)
    return report
