"""Read-only lookups the worker needs that no single repository offers.

Joins across Suppliers, Listings, Variants and mappings. Not responsible for writes.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, ApprovalChange, Listing, Mapping, Supplier, Variant


@dataclass(frozen=True)
class MappedRow:
    """A Variant and the ids of all its Listings, highest priority first."""

    variant_id: int
    gid: str
    sku: str
    listing_ids: list[int]


def supplier_listings(session: Session, supplier_id: int) -> list[tuple[int, str]]:
    """Return `(id, url)` of every Listing of the Supplier."""
    rows = session.execute(select(Listing.id, Listing.url).where(
        Listing.supplier_id == supplier_id).order_by(Listing.id)).all()
    return [(i, u) for i, u in rows]


def mapped_variants(session: Session, supplier_id: int) -> list[MappedRow]:
    """Return the Variants mapped to any of the Supplier's Listings.

    Each carries all of its Listings, including other Suppliers', because a
    Variant is Sold Out only when every one of them is Out of Stock.
    """
    ours = select(Mapping.variant_id).join(Listing, Listing.id == Mapping.listing_id).where(
        Listing.supplier_id == supplier_id)
    rows = session.execute(
        select(Variant, Mapping.listing_id).join(Mapping, Mapping.variant_id == Variant.id)
        .where(Variant.id.in_(ours)).order_by(Variant.id, Mapping.priority, Mapping.id)).all()
    result: dict[int, MappedRow] = {}
    for variant, listing_id in rows:
        result.setdefault(variant.id, MappedRow(variant.id, variant.shopify_variant_id,
                                                variant.sku, [])).listing_ids.append(listing_id)
    return list(result.values())


@dataclass(frozen=True)
class ApprovedChange:
    """One held change, as stored with its approval."""

    variant_id: int
    gid: str
    sku: str
    to_state: str
    quantity: int


def variant_listing_ids(session: Session, variant_id: int) -> list[int]:
    """Return the ids of every Listing mapped to the Variant."""
    return list(session.scalars(select(Mapping.listing_id).where(Mapping.variant_id == variant_id)))


def approved_changes(session: Session, approval_id: int) -> list[ApprovedChange] | None:
    """Return the changes of an approval that the owner approved, else None."""
    approval = session.get(Approval, approval_id)
    if approval is None or approval.state != "approved":
        return None
    rows = session.execute(
        select(ApprovalChange, Variant.shopify_variant_id, Variant.sku)
        .join(Variant, Variant.id == ApprovalChange.variant_id)
        .where(ApprovalChange.approval_id == approval_id).order_by(ApprovalChange.id)).all()
    return [ApprovedChange(c.variant_id, gid, sku, c.to_state, c.quantity) for c, gid, sku in rows]


@dataclass(frozen=True)
class VariantInfo:
    """A managed Variant: its Listings and the shortest check interval among their Suppliers.

    Shortest, because that is what the dashboard uses for Stale: a Variant read less
    often than its most frequent Supplier checks is overdue.
    """

    variant_id: int
    sku: str
    listing_ids: list[int]
    interval_min: int


def variant_info(session: Session, gid: str) -> VariantInfo | None:
    """Look a Variant up by its Shopify id; None if unknown or not mapped to any Listing."""
    variant = session.scalar(select(Variant).where(Variant.shopify_variant_id == gid))
    if variant is None:
        return None
    rows = session.execute(
        select(Mapping.listing_id, Supplier.interval_min)
        .join(Listing, Listing.id == Mapping.listing_id)
        .join(Supplier, Supplier.id == Listing.supplier_id)
        .where(Mapping.variant_id == variant.id)).all()
    if not rows:
        return None
    return VariantInfo(variant.id, variant.sku, [r[0] for r in rows], min(r[1] for r in rows))
