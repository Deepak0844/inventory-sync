"""Variants, Listings and the mappings between them.

Not responsible for parsing CSV files or for deciding Stock Status.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Integer, func, literal, select
from sqlalchemy.orm import Session

from app.db.models import (
    Listing,
    ListingStateRow,
    Mapping,
    Reading,
    Variant,
    VariantStateRow,
)

READING_STRIP = 12


@dataclass(frozen=True)
class ImportRow:
    """One CSV row, with the Supplier already resolved to its id."""

    sku: str
    supplier_id: int
    url: str
    selection_hint: str
    row_number: int = 0


@dataclass(frozen=True)
class RowError:
    row: int
    message: str


@dataclass(frozen=True)
class ImportResult:
    created: int
    updated: int
    errors: list[RowError]


@dataclass(frozen=True)
class ListingRow:
    id: int
    supplier_id: int
    url: str
    selection_hint: str
    status: str
    quantity: int | None
    removed: bool
    last_success_at: datetime | None


@dataclass(frozen=True)
class MappingRecord:
    listing_id: int
    supplier_id: int
    priority: int


@dataclass(frozen=True)
class ReadingPoint:
    result: str
    read_at: datetime


@dataclass(frozen=True)
class VariantRow:
    id: int
    shopify_variant_id: str
    sku: str
    title: str
    state: str | None
    sold_out_at: datetime | None
    listings: list[MappingRecord] = field(default_factory=list)
    readings: list[ReadingPoint] = field(default_factory=list)


@dataclass(frozen=True)
class ListingPage:
    items: list[ListingRow]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class VariantPage:
    items: list[VariantRow]
    total: int
    next_cursor: str | None


class CatalogRepo:
    """Reads and writes Variants, Listings and mappings."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert_variant(self, shopify_variant_id: str, sku: str, title: str) -> int:
        """Add or refresh a Variant by its Shopify id. Returns its id."""
        variant = self._s.scalar(select(Variant).where(
            Variant.shopify_variant_id == shopify_variant_id))
        if variant is None:
            variant = Variant(shopify_variant_id=shopify_variant_id, sku=sku, title=title)
            self._s.add(variant)
        else:
            variant.sku, variant.title = sku, title
        self._s.commit()
        return variant.id

    def import_rows(self, rows: list[ImportRow]) -> ImportResult:
        """Create or reuse each row's Listing and map it to the Variant with that SKU.

        A new mapping gets the next priority. A row with an unknown SKU is
        reported and the other rows are still applied.
        """
        created = updated = 0
        errors: list[RowError] = []
        for row in rows:
            variant = self._s.scalar(select(Variant).where(Variant.sku == row.sku))
            if variant is None:
                errors.append(RowError(row.row_number, f"Unknown SKU {row.sku}"))
                continue
            listing = self._s.scalar(select(Listing).where(
                Listing.supplier_id == row.supplier_id, Listing.url == row.url,
                Listing.selection_hint == row.selection_hint))
            if listing is None:
                listing = Listing(supplier_id=row.supplier_id, url=row.url,
                                  selection_hint=row.selection_hint)
                self._s.add(listing)
                self._s.flush()
                created += 1
            else:
                updated += 1
            if self._s.scalar(select(Mapping.id).where(
                    Mapping.variant_id == variant.id, Mapping.listing_id == listing.id)) is None:
                top = self._s.scalar(select(func.max(Mapping.priority)).where(
                    Mapping.variant_id == variant.id))
                self._s.add(Mapping(variant_id=variant.id, listing_id=listing.id,
                                    priority=(top or 0) + 1))
        self._s.commit()
        return ImportResult(created, updated, errors)

    def list_listings(
        self, supplier_id: int | None = None, q: str | None = None, status: str | None = None,
        cursor: str | None = None, limit: int = 50,
    ) -> ListingPage:
        """Page through Listings, newest id last, with their current state."""
        status_col = func.coalesce(ListingStateRow.status, literal("unknown"))
        query = (
            select(Listing, ListingStateRow)
            .outerjoin(ListingStateRow, ListingStateRow.listing_id == Listing.id)
        )
        if supplier_id is not None:
            query = query.where(Listing.supplier_id == supplier_id)
        if q:
            query = query.where(Listing.url.ilike(f"%{q}%"))
        if status:
            query = query.where(status_col == status)
        total = self._s.scalar(select(func.count()).select_from(query.subquery())) or 0
        if cursor:
            query = query.where(Listing.id > int(cursor))
        rows = self._s.execute(query.order_by(Listing.id).limit(limit + 1)).all()
        items = [
            ListingRow(lst.id, lst.supplier_id, lst.url, lst.selection_hint,
                       st.status if st else "unknown", st.quantity if st else None,
                       st.removed if st else False, st.last_success_at if st else None)
            for lst, st in rows[:limit]
        ]
        return ListingPage(items, total, str(items[-1].id) if len(rows) > limit else None)

    def get_mappings(self, variant_id: int) -> list[MappingRecord]:
        """Return a Variant's mappings, highest priority (lowest number) first."""
        rows = self._s.execute(
            select(Mapping.listing_id, Listing.supplier_id, Mapping.priority)
            .join(Listing, Listing.id == Mapping.listing_id)
            .where(Mapping.variant_id == variant_id).order_by(Mapping.priority)
        ).all()
        return [MappingRecord(*r) for r in rows]

    def set_mappings(self, variant_id: int, pairs: list[tuple[int, int]]) -> None:
        """Replace a Variant's mappings with `(listing_id, priority)` pairs."""
        self._s.query(Mapping).filter(Mapping.variant_id == variant_id).delete()
        self._s.flush()
        self._s.add_all(Mapping(variant_id=variant_id, listing_id=lid, priority=p)
                        for lid, p in pairs)
        self._s.commit()

    def list_variants(
        self, state: str | None = None, q: str | None = None, cursor: str | None = None,
        limit: int = 50,
    ) -> VariantPage:
        """Page through Variants with their mappings and the last 12 readings."""
        query = (
            select(Variant, VariantStateRow)
            .outerjoin(VariantStateRow, VariantStateRow.variant_id == Variant.id)
        )
        if state:
            query = query.where(VariantStateRow.state == state)
        if q:
            query = query.where(Variant.sku.ilike(f"%{q}%") | Variant.title.ilike(f"%{q}%"))
        total = self._s.scalar(select(func.count()).select_from(query.subquery())) or 0
        if cursor:
            query = query.where(Variant.id > int(cursor))
        rows = self._s.execute(query.order_by(Variant.id).limit(limit + 1)).all()[: limit + 1]
        page = rows[:limit]
        ids = [v.id for v, _ in page]
        mappings = {i: self.get_mappings(i) for i in ids}
        strips = self._readings(ids)
        items = [
            VariantRow(v.id, v.shopify_variant_id, v.sku, v.title, st.state if st else None,
                       st.sold_out_at if st else None, mappings[v.id], strips.get(v.id, []))
            for v, st in page
        ]
        return VariantPage(items, total, str(items[-1].id) if len(rows) > limit else None)

    def _readings(self, variant_ids: list[int]) -> dict[int, list[ReadingPoint]]:
        if not variant_ids:
            return {}
        ranked = (
            select(
                Mapping.variant_id.label("variant_id"), Reading.result.label("result"),
                Reading.read_at.label("read_at"),
                func.row_number().over(
                    partition_by=Mapping.variant_id,
                    order_by=(Reading.read_at.desc(), Reading.id.desc()),
                ).cast(Integer).label("rn"),
            )
            .join(Reading, Reading.listing_id == Mapping.listing_id)
            .where(Mapping.variant_id.in_(variant_ids)).subquery()
        )
        rows = self._s.execute(
            select(ranked.c.variant_id, ranked.c.result, ranked.c.read_at)
            .where(ranked.c.rn <= READING_STRIP).order_by(ranked.c.read_at)
        ).all()
        strips: dict[int, list[ReadingPoint]] = {}
        for variant_id, result, read_at in rows:
            strips.setdefault(variant_id, []).append(ReadingPoint(result, read_at))
        return strips
