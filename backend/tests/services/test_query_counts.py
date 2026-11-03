"""The banner and overview are polled constantly, so their cost must not grow with the catalog."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.db.repos.catalog import CatalogRepo, ImportRow
from app.db.repos.history import HistoryRepo
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SupplierRepo
from app.engine.listing import ListingState, StockStatus
from app.services import catalog
from app.services.overview import build_banner, build_overview

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
BOX = SecretBox(generate_key())


def seed(session: Session, first: int, last: int, supplier_id: int) -> None:
    """Variants first..last-1, each with one Listing, a state, a reading and a change."""
    for i in range(first, last):
        sku = f"SKU-{i}"
        variant = CatalogRepo(session).upsert_variant(f"gid://v/{i}", sku, sku)
        url = f"https://a.example/{i}"
        CatalogRepo(session).import_rows([ImportRow(sku, supplier_id, url, "")])
        listing = CatalogRepo(session).get_mappings(variant)[0].listing_id
        StateRepo(session).save_listing_state(
            listing,
            ListingState(StockStatus.OUT_OF_STOCK if i % 2 else StockStatus.IN_STOCK,
                         last_success_at=(NOW - timedelta(hours=i % 5)).timestamp()))
        HistoryRepo(session).add_reading(listing, "in_stock", None, None, NOW)
        StateRepo(session).save_variant_state(variant, "sold_out" if i % 2 else "available",
                                              NOW, None)
        HistoryRepo(session).record_change(variant, None, "sold_out", "r", "auto", NOW)


def statements(engine: Engine, work: Callable[[], object]) -> int:
    seen: list[str] = []

    def count(conn: Connection, cursor: object, statement: str, *rest: object) -> None:
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        work()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(seen)


@pytest.mark.parametrize("stale", [None, True, False])
def test_variant_pages_cost_the_same_number_of_queries_for_any_catalog_size(
    db_session: Session, stale: bool | None
) -> None:
    engine = db_session.get_bind()
    assert isinstance(engine, Engine)
    supplier = SupplierRepo(db_session, BOX).create("A", "https://a.example", NOW).id

    def page() -> object:
        return catalog.list_variants(db_session, BOX, NOW, None, stale, None, None, 50)

    seed(db_session, 0, 3, supplier)
    small = statements(engine, page)
    seed(db_session, 3, 40, supplier)
    assert statements(engine, page) == small


def test_overview_and_banner_cost_the_same_number_of_queries_for_any_catalog_size(
    db_session: Session,
) -> None:
    engine = db_session.get_bind()
    assert isinstance(engine, Engine)
    supplier = SupplierRepo(db_session, BOX).create("A", "https://a.example", NOW).id

    def both() -> object:
        return build_overview(db_session, BOX, NOW), build_banner(db_session, BOX, NOW)

    seed(db_session, 0, 3, supplier)
    small = statements(engine, both)
    seed(db_session, 3, 40, supplier)
    assert statements(engine, both) == small


def test_the_overview_numbers_are_still_right(db_session: Session) -> None:
    supplier = SupplierRepo(db_session, BOX).create("A", "https://a.example", NOW).id
    seed(db_session, 0, 6, supplier)
    overview = build_overview(db_session, BOX, NOW)
    assert (overview.sold_out, overview.in_stock) == (3, 3)
    assert overview.sold_out_by_day[-1].count == 6  # every seeded change says sold_out
    assert build_banner(db_session, BOX, NOW).approvals == 0


def test_the_stale_filter_pages_without_skipping_or_repeating(db_session: Session) -> None:
    supplier = SupplierRepo(db_session, BOX).create("A", "https://a.example", NOW).id
    seed(db_session, 0, 9, supplier)
    for variant in CatalogRepo(db_session).list_variants(limit=100).items:
        if variant.id % 3 == 0:  # a few variants whose Listing was last read long ago
            listing = variant.listings[0].listing_id
            StateRepo(db_session).save_listing_state(
                listing, ListingState(StockStatus.IN_STOCK,
                                      last_success_at=(NOW - timedelta(days=3)).timestamp()))
    seen: list[int] = []
    cursor: str | None = None
    while True:
        page = catalog.list_variants(db_session, BOX, NOW, None, True, None, cursor, 2)
        assert page.total == 3
        seen += [v.row.id for v in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == [3, 6, 9]
