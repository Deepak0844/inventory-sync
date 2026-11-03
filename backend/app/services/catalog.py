"""Listings, Variants and mappings: CSV import, the Variant list with Stale, mapping edits.

Not responsible for HTTP or for deciding Stock Status (`app.engine`).
"""

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.catalog import (
    CatalogRepo,
    ImportRow,
    ListingPage,
    MappingRecord,
    RowError,
    VariantRow,
)
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SupplierRepo
from app.engine.safety import is_variant_stale

MAX_IMPORT_BYTES = 1_048_576
MAX_IMPORT_ROWS = 10_000
_REQUIRED = ("sku", "supplier", "url")
_PAGE = 500


class ImportRejected(Exception):
    """The whole file is unusable (bad header, too big, not text)."""


class UnknownVariant(Exception):
    """No Variant has this id."""


class InvalidMapping(Exception):
    """The mapping names a Listing that does not exist, or repeats one."""


@dataclass(frozen=True)
class ImportOutcome:
    """What a CSV import did. Rows that failed are listed; the others were applied."""

    created: int
    updated: int
    errors: list[RowError]


@dataclass(frozen=True)
class VariantView:
    """A Variant row plus whether it is Stale."""

    row: VariantRow
    stale: bool


@dataclass(frozen=True)
class VariantsView:
    items: list[VariantView]
    total: int
    next_cursor: str | None


def parse_import_csv(
    text: str, supplier_ids: Mapping[str, int]
) -> tuple[list[ImportRow], list[RowError]]:
    """Turn CSV text into import rows, reporting each bad row instead of failing the file.

    Args:
        text: The file contents. Columns `sku,supplier,url` plus optional `selection_hint`,
            in any order and case. `supplier` is the Supplier's name.
        supplier_ids: Supplier name to id.

    Returns:
        The valid rows (row numbers are spreadsheet rows, so the first data row is 2) and
        one error per bad row.

    Raises:
        ImportRejected: for a missing required column or more than 10000 rows.
    """
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in next(reader, [])]
    if any(c not in header for c in _REQUIRED):
        raise ImportRejected("The first row must name the columns sku, supplier and url")
    column = {name: header.index(name) for name in header}
    rows: list[ImportRow] = []
    errors: list[RowError] = []
    for number, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        if number - 1 > MAX_IMPORT_ROWS:
            raise ImportRejected(f"At most {MAX_IMPORT_ROWS} rows per file")
        if len(cells) < len(_REQUIRED) or len(cells) <= max(column[c] for c in _REQUIRED):
            errors.append(RowError(number, "Row has too few columns"))
            continue
        sku, supplier, url = (cells[column[c]].strip() for c in _REQUIRED)
        hint = cells[column["selection_hint"]].strip() if "selection_hint" in column \
            and column["selection_hint"] < len(cells) else ""
        problem = _row_problem(sku, supplier, url, supplier_ids)
        if problem:
            errors.append(RowError(number, problem))
        else:
            rows.append(ImportRow(sku, supplier_ids[supplier], url, hint, number))
    return rows, errors


def _row_problem(sku: str, supplier: str, url: str, supplier_ids: Mapping[str, int]) -> str | None:
    if not sku:
        return "SKU is empty"
    if supplier not in supplier_ids:
        return f"Unknown Supplier {supplier}"
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        return "URL must start with http:// or https://"
    return None


def import_listings(session: Session, box: SecretBox, data: bytes) -> ImportOutcome:
    """Import a CSV of `sku,supplier,url[,selection_hint]`, mapping each Listing to its Variant.

    Valid rows are applied even when others fail. Re-importing a file updates, not duplicates.

    Raises:
        ImportRejected: if the file is too large, not UTF-8, or has a bad header.
    """
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportRejected("The file is larger than 1 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportRejected("The file must be UTF-8 text") from None
    suppliers = {s.name: s.id for s in SupplierRepo(session, box).list()}
    rows, errors = parse_import_csv(text, suppliers)
    result = CatalogRepo(session).import_rows(rows)
    merged = sorted([*errors, *result.errors], key=lambda e: e.row)
    return ImportOutcome(result.created, result.updated, merged)


def list_listings(
    session: Session, supplier_id: int | None, q: str | None, status: str | None,
    cursor: str | None, limit: int,
) -> ListingPage:
    """Page through Listings with their current state."""
    return CatalogRepo(session).list_listings(supplier_id, q, status, cursor, limit)


def _stale_flags(
    session: Session, box: SecretBox, now: datetime, rows: list[VariantRow]
) -> dict[int, bool]:
    """Stale per Variant, using the shortest interval among its Suppliers.

    The shortest is the strictest: it flags a Variant a little early rather than late,
    which only costs an extra "verify with Supplier" on an order.
    """
    intervals = {s.id: s.interval_min * 60.0 for s in SupplierRepo(session, box).list()}
    states = StateRepo(session)
    flags: dict[int, bool] = {}
    for row in rows:
        listing_states = [states.get_listing_state(m.listing_id) for m in row.listings]
        interval = min((intervals[m.supplier_id] for m in row.listings), default=0.0)
        flags[row.id] = is_variant_stale(listing_states, now.timestamp(), interval)
    return flags


def list_variants(
    session: Session, box: SecretBox, now: datetime, state: str | None, stale: bool | None,
    q: str | None, cursor: str | None, limit: int,
) -> VariantsView:
    """Page through Variants with mappings, the reading strip and whether each is Stale.

    With a `stale` filter every matching Variant is checked first, so `total` stays honest.
    """
    repo = CatalogRepo(session)
    if stale is None:
        page = repo.list_variants(state, q, cursor, limit)
        flags = _stale_flags(session, box, now, page.items)
        return VariantsView([VariantView(r, flags[r.id]) for r in page.items], page.total,
                            page.next_cursor)
    matching: list[VariantView] = []
    after: str | None = None
    while True:
        page = repo.list_variants(state, q, after, _PAGE)
        flags = _stale_flags(session, box, now, page.items)
        matching += [VariantView(r, flags[r.id]) for r in page.items if flags[r.id] is stale]
        if page.next_cursor is None:
            break
        after = page.next_cursor
    start = [v for v in matching if cursor is None or v.row.id > int(cursor)]
    items = start[:limit]
    more = len(start) > limit
    return VariantsView(items, len(matching), str(items[-1].row.id) if more else None)


def get_mappings(session: Session, variant_id: int) -> list[MappingRecord]:
    """Return a Variant's mappings, highest priority first. Raises UnknownVariant."""
    repo = CatalogRepo(session)
    if not repo.variant_exists(variant_id):
        raise UnknownVariant(variant_id)
    return repo.get_mappings(variant_id)


def replace_mappings(
    session: Session, variant_id: int, pairs: list[tuple[int, int]]
) -> list[MappingRecord]:
    """Replace a Variant's mappings with `(listing_id, priority)` pairs.

    Raises:
        UnknownVariant: for an unknown Variant.
        InvalidMapping: for an unknown or repeated Listing; nothing is changed.
    """
    repo = CatalogRepo(session)
    if not repo.variant_exists(variant_id):
        raise UnknownVariant(variant_id)
    ids = [listing_id for listing_id, _ in pairs]
    if len(set(ids)) != len(ids) or repo.existing_listing_ids(ids) != set(ids):
        raise InvalidMapping("Each mapped Listing must exist and appear once")
    repo.set_mappings(variant_id, pairs)
    return repo.get_mappings(variant_id)


