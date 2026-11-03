from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select

from app.db.models import Job
from app.db.repos.approvals import ApprovalRepo
from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SupplierRepo
from app.engine.listing import StockStatus
from app.worker.check import handle_check_supplier
from tests.worker.conftest import World

JOB = JobRecord(1, "check_supplier", None, {}, 0)
IN, OUT = "In stock", "Out of stock"


def check(world: World) -> None:
    with world.deps.session_factory() as session:
        handle_check_supplier(world.deps, session, JobRecord(1, "check_supplier",
                                                             world.supplier_id, {}, 0))


def kinds(world: World) -> list[str]:
    return [n.kind for n in NotificationRepo(world.session).list(resolved=False)]


def test_first_in_stock_reading_sets_the_variant_available(make_world: Callable[..., World]
                                                          ) -> None:
    w = make_world(variants=1)
    w.set_stock(IN)
    check(w)
    assert w.shopify.writes == [(w.gids[0], 100)]
    assert StateRepo(w.session).get_listing_state(1).status is StockStatus.IN_STOCK
    assert len(HistoryRepo(w.session).recent_readings(1, 5)) == 1


def test_one_out_of_stock_reading_changes_nothing_and_schedules_a_confirmation(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.set_stock(IN)
    check(w)
    w.shopify.writes.clear()
    w.set_stock(OUT)
    w.clock.sleep(7200)
    check(w)
    assert w.shopify.writes == [(w.gids[0], 100)]  # still available: refreshed, not sold out
    job = w.session.scalars(select(Job).where(Job.kind == "check_supplier")).one()
    assert job.run_after == w.now() + timedelta(minutes=30)


def test_two_out_of_stock_readings_half_an_hour_apart_sell_the_variant_out(
    make_world: Callable[..., World],
) -> None:
    # Four Listings so one flip is 25%, under the kill switch.
    w = make_world(variants=4)
    w.set_stock(IN, IN, IN, IN)
    check(w)
    w.set_stock(OUT, IN, IN, IN)
    w.clock.sleep(7200)
    check(w)
    w.shopify.writes.clear()
    w.clock.sleep(1800)
    check(w)
    assert (w.gids[0], 0) in w.shopify.writes
    assert StateRepo(w.session).get_variant_state(1).state == "sold_out"  # type: ignore[union-attr]
    change = [c for c in HistoryRepo(w.session).recent_changes(5) if c.variant_id == 1][0]
    assert (change.to_state, change.reason, change.approval) == (
        "sold_out", "all_out_of_stock", "auto")


def test_a_listing_that_cannot_be_read_is_unknown_and_never_writes(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=2)
    w.set_stock(IN, IN)
    check(w)
    w.shopify.writes.clear()
    w.set_stock(None, None)  # the stock element vanished: a site redesign
    w.clock.sleep(7200)
    check(w)
    assert w.shopify.writes == []
    assert "flow_failure" in kinds(w)
    assert StateRepo(w.session).get_listing_state(1).status is StockStatus.IN_STOCK


def test_a_mass_flip_is_held_for_approval_and_writes_nothing(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=4)
    w.set_stock(IN, IN, IN, IN)
    check(w)
    w.set_stock(OUT, OUT, OUT, OUT)
    w.clock.sleep(7200)
    check(w)
    w.shopify.writes.clear()
    w.clock.sleep(1800)
    check(w)
    assert w.shopify.writes == []
    pending = ApprovalRepo(w.session).list_pending()
    assert len(pending) == 1 and len(pending[0].changes) == 4
    assert "pending_approval" in kinds(w)
    assert StateRepo(w.session).get_variant_state(1).state == "available"  # type: ignore[union-attr]


def test_an_in_stock_reading_restores_a_sold_out_variant(make_world: Callable[..., World]) -> None:
    w = make_world(variants=4)
    w.set_stock(OUT, IN, IN, IN)
    check(w)
    w.clock.sleep(1800)
    check(w)
    assert (w.gids[0], 0) in w.shopify.writes
    w.set_stock(IN, IN, IN, IN)
    w.clock.sleep(7200)
    w.shopify.writes.clear()
    check(w)
    assert (w.gids[0], 100) in w.shopify.writes
    restore = [c for c in HistoryRepo(w.session).recent_changes(9) if c.variant_id == 1][0]
    assert restore.reason == "restore"


def test_a_shopify_error_for_one_variant_is_reported_and_the_rest_still_apply(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=2)
    w.shopify.fail_for = {"gid://shopify/ProductVariant/1"}
    w.set_stock(IN, IN)
    check(w)
    assert w.shopify.writes == [("gid://shopify/ProductVariant/2", 100)]
    assert "shopify_error" in kinds(w)


def test_without_shopify_settings_nothing_is_written_and_the_owner_is_told(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.deps.shopify = lambda settings, secrets: None
    w.set_stock(IN)
    check(w)
    assert w.shopify.writes == [] and "shopify_error" in kinds(w)


def test_a_removed_listing_is_flagged_for_review(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    w.page.removed = {"http://supplier.test/p/1"}
    w.set_stock(IN)
    check(w)
    assert "listing_removed" in kinds(w)


def test_a_successful_check_updates_the_suppliers_last_success(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.set_stock(IN)
    check(w)
    supplier = SupplierRepo(w.session, w.box).get(w.supplier_id)
    assert supplier is not None and supplier.last_success_at == w.now()


def test_a_paused_supplier_is_not_checked(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1, paused=True)
    w.set_stock(IN)
    check(w)
    assert w.shopify.writes == [] and w.page.visited == []
