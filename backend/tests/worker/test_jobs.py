from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select

from app.db.models import Job
from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.catalog import CatalogRepo
from app.db.repos.codes import PastedCodeRepo
from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRecord, JobRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import OrderRepo
from app.db.repos.runs import RunRepo
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SessionCookiesRepo
from app.engine.listing import ListingState, StockStatus
from app.shopify.orders import Order
from app.shopify.variants import ShopVariant
from app.worker.approval import handle_apply_approval
from app.worker.jobs import HANDLERS, run_once
from app.worker.login import handle_login
from app.worker.orders import handle_poll_orders
from app.worker.summary import handle_daily_summary
from app.worker.sync import handle_sync_variants
from tests.worker.conftest import World
from tests.worker.test_login import LoginSite, logged_out_world


def job(kind: str, w: World, **payload: object) -> JobRecord:
    return JobRecord(1, kind, w.supplier_id, dict(payload), 0)


def kinds(w: World) -> list[str]:
    return [n.kind for n in NotificationRepo(w.session).list(resolved=False)]


# --- approvals -----------------------------------------------------------------


def held(w: World) -> int:
    StateRepo(w.session).save_variant_state(1, "available", w.now(), 100)
    return ApprovalRepo(w.session).create(
        w.supplier_id, [HeldChange(1, "available", "sold_out", 0)], w.now())


def apply(w: World, approval_id: int) -> None:
    with w.deps.session_factory() as s:
        handle_apply_approval(w.deps, s, job("apply_approval", w, approval_id=approval_id))


def test_an_approved_batch_is_written_and_recorded_as_manual(make_world: Callable[..., World]
                                                            ) -> None:
    w = make_world(variants=1)
    approval = held(w)
    ApprovalRepo(w.session).decide(approval, True, w.now())
    apply(w, approval)
    assert w.shopify.writes == [(w.gids[0], 0)]
    assert StateRepo(w.session).get_variant_state(1).state == "sold_out"  # type: ignore[union-attr]
    assert HistoryRepo(w.session).recent_changes(1)[0].approval == "manual"


def test_a_rejected_or_undecided_batch_writes_nothing(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    approval = held(w)
    apply(w, approval)  # still pending
    ApprovalRepo(w.session).decide(approval, False, w.now())
    apply(w, approval)
    assert w.shopify.writes == []


# --- variants ------------------------------------------------------------------


def test_sync_variants_adds_and_refreshes_variants_and_skips_a_duplicate_sku(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    w.shopify.variants = [
        ShopVariant("gid://shopify/ProductVariant/1", "SKU1", "Renamed"),
        ShopVariant("gid://shopify/ProductVariant/9", "NEW", "New shirt"),
        ShopVariant("gid://shopify/ProductVariant/10", "NEW", "Same sku, other variant"),
    ]
    with w.deps.session_factory() as s:
        handle_sync_variants(w.deps, s, JobRecord(1, "sync_variants", None, {}, 0))
    titles = {v.sku: v.title for v in CatalogRepo(w.session).list_variants(limit=50).items}
    assert titles["SKU1"] == "Renamed" and titles["NEW"] == "New shirt" and len(titles) == 2


def test_sync_variants_without_shopify_settings_tells_the_owner(make_world: Callable[..., World]
                                                               ) -> None:
    w = make_world(variants=1)
    w.deps.shopify = lambda settings, secrets: None
    with w.deps.session_factory() as s:
        handle_sync_variants(w.deps, s, JobRecord(1, "sync_variants", None, {}, 0))
    assert "shopify_error" in kinds(w)


# --- orders --------------------------------------------------------------------


def order(id: str, *gids: str, truncated: bool = False) -> Order:
    return Order(id, f"#{id}", "2026-11-03T10:00:00Z", tuple(gids), truncated)


def poll(w: World) -> None:
    with w.deps.session_factory() as s:
        handle_poll_orders(w.deps, s, JobRecord(1, "poll_orders", None,
                                                {"since": "2026-11-03T09:00:00Z"}, 0))


def fresh(w: World, listing_id: int, status: StockStatus) -> None:
    StateRepo(w.session).save_listing_state(listing_id, ListingState(
        status=status, last_success_at=w.clock.now() - 600))


def flagged(w: World) -> dict[str, list[tuple[str, str]]]:
    return {o.order_id: [(x.sku, x.reason) for x in o.lines]
            for o in OrderRepo(w.session).list_flagged()}


def test_an_order_with_a_stale_variant_is_flagged(make_world: Callable[..., World]) -> None:
    w = make_world(variants=2)
    fresh(w, 1, StockStatus.IN_STOCK)  # variant 1 is fresh, variant 2 was never checked
    w.shopify.orders = [order("A", w.gids[0]), order("B", w.gids[1])]
    poll(w)
    assert flagged(w) == {"B": [("SKU2", "stale")]}


def test_an_order_with_a_variant_sold_out_recently_is_flagged(make_world: Callable[..., World]
                                                             ) -> None:
    w = make_world(variants=1)
    fresh(w, 1, StockStatus.OUT_OF_STOCK)
    StateRepo(w.session).save_variant_state(1, "sold_out", w.now() - timedelta(hours=2), 0)
    w.shopify.orders = [order("A", w.gids[0])]
    poll(w)
    assert flagged(w) == {"A": [("SKU1", "recently_sold_out")]}


def test_a_sold_out_variant_from_a_week_ago_is_not_a_reason_to_flag(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    fresh(w, 1, StockStatus.OUT_OF_STOCK)
    StateRepo(w.session).save_variant_state(1, "sold_out", w.now() - timedelta(days=7), 0)
    w.shopify.orders = [order("A", w.gids[0])]
    poll(w)
    assert flagged(w) == {}


def test_a_truncated_order_is_flagged_even_if_every_seen_line_is_fine(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    fresh(w, 1, StockStatus.IN_STOCK)
    w.shopify.orders = [order("A", w.gids[0], truncated=True)]
    poll(w)
    assert [o.lines_truncated for o in OrderRepo(w.session).list_flagged()] == [True]


def test_unmapped_variants_and_repeat_polls_do_not_flag_twice(make_world: Callable[..., World]
                                                             ) -> None:
    w = make_world(variants=1)
    w.shopify.orders = [order("A", "gid://shopify/ProductVariant/999", w.gids[0])]
    poll(w)
    poll(w)  # polls overlap, so the same order comes back
    assert flagged(w) == {"A": [("SKU1", "stale")]}
    assert w.shopify.since == ["2026-11-03T09:00:00Z"] * 2


# --- summary, login job, dispatcher ----------------------------------------------


def test_the_daily_summary_counts_what_the_owner_cares_about(make_world: Callable[..., World]
                                                            ) -> None:
    w = make_world(variants=2)
    held(w)
    StateRepo(w.session).save_variant_state(2, "sold_out", w.now(), 0)
    with w.deps.session_factory() as s:
        handle_daily_summary(w.deps, s, JobRecord(1, "daily_summary", None, {}, 0))
    note = [n for n in NotificationRepo(w.session).list(resolved=False)
            if n.kind == "daily_summary"][0]
    assert "1 sold out" in note.message and "1 waiting for approval" in note.message


def test_the_login_button_job_logs_in_and_saves_the_session(make_world: Callable[..., World]
                                                           ) -> None:
    w = logged_out_world(make_world, LoginSite())
    PastedCodeRepo(w.session, w.box).submit(w.supplier_id, "111111", w.now())
    with w.deps.session_factory() as s:
        handle_login(w.deps, s, job("login", w))
    assert SessionCookiesRepo(w.session, w.supplier_id, w.now).get() is not None
    assert [r.kind for r in RunRepo(w.session).list_for_supplier(w.supplier_id)] == ["login"]


def test_every_job_kind_has_a_handler() -> None:
    assert set(HANDLERS) == {"check_supplier", "login", "apply_approval", "sync_variants",
                             "poll_orders", "daily_summary"}


def test_run_once_returns_false_when_the_queue_is_empty(make_world: Callable[..., World]) -> None:
    assert run_once(make_world(variants=1).deps) is False


def test_run_once_completes_a_job(make_world: Callable[..., World]) -> None:
    w = make_world(variants=1)
    w.set_stock("In stock")
    JobRepo(w.session).enqueue("check_supplier", w.supplier_id, {}, w.now(), w.now())
    assert run_once(w.deps) is True
    assert w.session.scalars(select(Job.state)).all() == ["done"]
    assert w.shopify.writes == [(w.gids[0], 100)]


def test_a_crashing_job_is_retried_later_and_the_worker_carries_on(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)

    def boom(deps: object, session: object, job: object) -> None:
        raise RuntimeError("bug")

    HANDLERS["daily_summary"], original = boom, HANDLERS["daily_summary"]
    try:
        JobRepo(w.session).enqueue("daily_summary", None, {}, w.now(), w.now())
        assert run_once(w.deps) is True
    finally:
        HANDLERS["daily_summary"] = original
    row = w.session.scalars(select(Job)).one()
    assert (row.state, row.attempts, "bug" in (row.last_error or "")) == ("queued", 1, True)
    assert row.run_after > w.now()


def test_a_job_of_an_unknown_kind_fails_instead_of_blocking_the_queue(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    JobRepo(w.session).enqueue("nonsense", None, {}, w.now(), w.now())
    assert run_once(w.deps) is True
    assert w.session.scalars(select(Job.attempts)).one() == 1
