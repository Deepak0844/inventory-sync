from sqlalchemy.orm import Session

from app.db.repos.catalog import CatalogRepo
from app.db.repos.history import HistoryRepo
from app.db.repos.states import StateRepo
from app.engine.listing import ListingState, StockStatus
from tests.db.helpers import NOW, later, make_supplier


def one_listing(db_session: Session) -> tuple[int, int]:
    from app.db.repos.catalog import ImportRow

    catalog = CatalogRepo(db_session)
    supplier = make_supplier(db_session)
    catalog.upsert_variant("gid://v/1", "SKU-1", "T")
    catalog.import_rows([ImportRow("SKU-1", supplier, "https://a.example/1", "")])
    return catalog.list_listings().items[0].id, catalog.list_variants().items[0].id


def test_a_listing_with_no_row_is_unknown(db_session: Session) -> None:
    listing_id, _ = one_listing(db_session)
    assert StateRepo(db_session).get_listing_state(listing_id) == ListingState()


def test_listing_state_round_trips(db_session: Session) -> None:
    listing_id, _ = one_listing(db_session)
    states = StateRepo(db_session)
    state = ListingState(status=StockStatus.IN_STOCK, removed=True, last_success_at=1_000.5,
                         quantity=7, streak_kind=StockStatus.OUT_OF_STOCK, streak_count=1,
                         streak_last_at=900.0)
    states.save_listing_state(listing_id, state)
    assert states.get_listing_state(listing_id) == state
    states.save_listing_state(listing_id, ListingState(status=StockStatus.OUT_OF_STOCK))
    assert states.get_listing_state(listing_id).status is StockStatus.OUT_OF_STOCK


def test_variant_with_no_row_is_not_managed(db_session: Session) -> None:
    _, variant_id = one_listing(db_session)
    assert StateRepo(db_session).get_variant_state(variant_id) is None


def test_sold_out_at_is_kept_until_the_variant_is_restored(db_session: Session) -> None:
    _, variant_id = one_listing(db_session)
    states = StateRepo(db_session)
    states.save_variant_state(variant_id, "sold_out", NOW, 0)
    states.save_variant_state(variant_id, "sold_out", later(60), 0)
    record = states.get_variant_state(variant_id)
    assert record is not None and record.sold_out_at == NOW
    states.save_variant_state(variant_id, "available", later(120), 100)
    record = states.get_variant_state(variant_id)
    assert record is not None and record.sold_out_at is None
    assert record.last_written_quantity == 100


def test_readings_and_changes_are_recorded_newest_first(db_session: Session) -> None:
    listing_id, variant_id = one_listing(db_session)
    history = HistoryRepo(db_session)
    history.add_reading(listing_id, "unknown", "flow_failure", None, NOW, "shots/1.png")
    history.add_reading(listing_id, "in_stock", None, 4, later(60))
    recent = history.recent_readings(listing_id, 5)
    assert [r.result for r in recent] == ["in_stock", "unknown"]
    assert recent[1].error_kind == "flow_failure" and recent[1].screenshot_path == "shots/1.png"
    history.record_change(variant_id, None, "available", "first_sync", "auto", NOW)
    history.record_change(variant_id, "available", "sold_out", "all_out_of_stock", "approved",
                          later(60))
    changes = history.recent_changes(10)
    assert [c.to_state for c in changes] == ["sold_out", "available"]
    assert changes[0].sku == "SKU-1" and changes[0].approval == "approved"
