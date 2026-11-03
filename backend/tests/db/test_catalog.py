from sqlalchemy.orm import Session

from app.db.repos.catalog import CatalogRepo, ImportRow
from app.db.repos.history import HistoryRepo
from tests.db.helpers import NOW, later, make_supplier


def add_variants(catalog: CatalogRepo, *skus: str) -> None:
    for sku in skus:
        catalog.upsert_variant(f"gid://shopify/ProductVariant/{sku}", sku, f"Title {sku}")


def test_import_creates_listings_and_mappings(db_session: Session) -> None:
    catalog = CatalogRepo(db_session)
    supplier = make_supplier(db_session)
    add_variants(catalog, "SKU-1", "SKU-2")
    result = catalog.import_rows([
        ImportRow("SKU-1", supplier, "https://a.example/p/1", ""),
        ImportRow("SKU-2", supplier, "https://a.example/p/2", "Black / L"),
    ])
    assert (result.created, result.updated, result.errors) == (2, 0, [])
    page = catalog.list_listings(supplier_id=supplier)
    assert page.total == 2 and {i.selection_hint for i in page.items} == {"", "Black / L"}


def test_import_twice_updates_instead_of_duplicating(db_session: Session) -> None:
    catalog = CatalogRepo(db_session)
    supplier = make_supplier(db_session)
    add_variants(catalog, "SKU-1")
    row = ImportRow("SKU-1", supplier, "https://a.example/p/1", "")
    catalog.import_rows([row])
    result = catalog.import_rows([row])
    assert (result.created, result.updated) == (0, 1)
    assert catalog.list_listings().total == 1


def test_import_reports_unknown_sku_and_still_applies_the_valid_rows(
    db_session: Session,
) -> None:
    catalog = CatalogRepo(db_session)
    supplier = make_supplier(db_session)
    add_variants(catalog, "SKU-1")
    result = catalog.import_rows([
        ImportRow("NOPE", supplier, "https://a.example/p/9", "", row_number=2),
        ImportRow("SKU-1", supplier, "https://a.example/p/1", "", row_number=3),
    ])
    assert result.created == 1
    assert [(e.row, "NOPE" in e.message) for e in result.errors] == [(2, True)]


def test_two_listings_map_with_priority_and_priority_replace(db_session: Session) -> None:
    catalog = CatalogRepo(db_session)
    a, b = make_supplier(db_session, "A"), make_supplier(db_session, "B")
    add_variants(catalog, "SKU-1")
    catalog.import_rows([
        ImportRow("SKU-1", a, "https://a.example/1", ""),
        ImportRow("SKU-1", b, "https://b.example/1", ""),
    ])
    variant = catalog.list_variants().items[0]
    assert [m.priority for m in variant.listings] == [1, 2]
    first, second = (m.listing_id for m in variant.listings)
    catalog.set_mappings(variant.id, [(second, 1), (first, 2)])
    assert [m.listing_id for m in catalog.get_mappings(variant.id)] == [second, first]


def test_variant_list_carries_the_last_12_readings_oldest_first(db_session: Session) -> None:
    catalog, history = CatalogRepo(db_session), HistoryRepo(db_session)
    supplier = make_supplier(db_session)
    add_variants(catalog, "SKU-1")
    catalog.import_rows([ImportRow("SKU-1", supplier, "https://a.example/1", "")])
    listing_id = catalog.list_listings().items[0].id
    for i in range(15):
        history.add_reading(listing_id, "in_stock" if i % 2 else "out_of_stock", None, None,
                            later(i * 60))
    readings = catalog.list_variants().items[0].readings
    assert len(readings) == 12
    assert [r.read_at for r in readings] == sorted(r.read_at for r in readings)
    assert readings[-1].read_at == later(14 * 60)


def test_variant_search_and_cursor_paging(db_session: Session) -> None:
    catalog = CatalogRepo(db_session)
    add_variants(catalog, "AAA-1", "AAA-2", "BBB-1")
    assert [v.sku for v in catalog.list_variants(q="BBB").items] == ["BBB-1"]
    first = catalog.list_variants(limit=2)
    assert len(first.items) == 2 and first.total == 3 and first.next_cursor is not None
    rest = catalog.list_variants(limit=2, cursor=first.next_cursor)
    assert len(rest.items) == 1 and rest.next_cursor is None


def test_variant_state_filter(db_session: Session) -> None:
    from app.db.repos.states import StateRepo

    catalog, states = CatalogRepo(db_session), StateRepo(db_session)
    add_variants(catalog, "SKU-1", "SKU-2")
    v1 = catalog.list_variants().items[0].id
    states.save_variant_state(v1, "sold_out", NOW, 0)
    assert [v.sku for v in catalog.list_variants(state="sold_out").items] == ["SKU-1"]
    assert catalog.list_variants(state="sold_out").items[0].sold_out_at == NOW
