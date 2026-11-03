"""The unit passed from the decision engine to the safety layer and to Shopify.

Plain data only. Not responsible for deciding or applying a change.
"""

from dataclasses import dataclass

from app.engine.variant import Decision


@dataclass(frozen=True)
class VariantChange:
    """A decision for one Shopify Variant (`variant_id` is its Shopify GID)."""

    variant_id: str
    decision: Decision
