import threading
import time
from collections.abc import Callable
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Job
from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import OrderRepo
from app.db.repos.states import StateRepo
from app.db.repos.suppliers import SupplierRepo
from app.engine.listing import ListingState, StockStatus
from app.shopify.orders import Order
from app.worker import queries
from app.worker.approval import ApprovalNotApplied, handle_apply_approval
from app.worker.jobs import serve
from app.worker.orders import handle_poll_orders
from tests.worker.conftest import BASE, World
from tests.worker.test_check import IN, OUT, check


def held_two(w: World) -> int:
    for variant_id in (1, 2):
        StateRepo(w.session).save_variant_state(variant_id, "available", w.now(), 100)
    return ApprovalRepo(w.session).create(w.supplier_id, [
        HeldChange(1, "available", "sold_out", 0), HeldChange(2, "available", "sold_out", 0)],
        w.now())


def apply(w: World, approval_id: int) -> None:
    with w.deps.session_factory() as s:
        handle_apply_approval(w.deps, s, JobRecord(1, "apply_approval", w.supplier_id,
                                                   {"approval_id": approval_id}, 0))


# --- 1. an approved batch is not lost ---------------------------------------------


def test_approved_changes_are_retried_when_shopify_is_unavailable(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=2)
    approval = held_two(w)
    ApprovalRepo(w.session).decide(approval, True, w.now())
    w.deps.shopify = lambda settings, secrets: None
    with pytest.raises(ApprovalNotApplied):
        apply(w, approval)
    assert "shopify_error" in [n.kind for n in NotificationRepo(w.session).list(resolved=False)]
    w.deps.shopify = lambda settings, secrets: w.shopify
    apply(w, approval)
    assert sorted(w.shopify.writes) == sorted([(w.gids[0], 0), (w.gids[1], 0)])


def test_a_retry_only_rewrites_what_failed(make_world: Callable[..., World]) -> None:
    w = make_world(variants=2)
    approval = held_two(w)
    ApprovalRepo(w.session).decide(approval, True, w.now())
    w.shopify.fail_for = {w.gids[1]}
    with pytest.raises(ApprovalNotApplied):
        apply(w, approval)
    assert w.shopify.writes == [(w.gids[0], 0)]
    w.shopify.fail_for = set()
    apply(w, approval)
    assert w.shopify.writes == [(w.gids[0], 0), (w.gids[1], 0)]


# --- 2. a day-old approval cannot sell out a restocked item -------------------------


def test_an_approved_sell_out_is_skipped_when_a_listing_is_in_stock_again(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=2)
    approval = held_two(w)
    StateRepo(w.session).save_listing_state(1, ListingState(
        status=StockStatus.IN_STOCK, last_success_at=w.clock.now()))
    ApprovalRepo(w.session).decide(approval, True, w.now())
    apply(w, approval)
    assert w.shopify.writes == [(w.gids[1], 0)]
    assert StateRepo(w.session).get_variant_state(1).state == "available"  # type: ignore[union-attr]
    skipped = [n for n in NotificationRepo(w.session).list(resolved=False)
               if n.kind == "pending_approval"]
    assert len(skipped) == 1 and "SKU1" in skipped[0].message and "in stock" in skipped[0].message


# --- 3. new held changes are merged into the pending approval -----------------------


def test_new_held_changes_join_the_pending_approval_and_the_notice_matches(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=4)
    w.set_stock(IN, IN, IN, IN)
    check(w)
    ApprovalRepo(w.session).create(
        w.supplier_id, [HeldChange(1, "available", "sold_out", 0)], w.now())
    NotificationRepo(w.session).add("pending_approval", w.supplier_id, "old: 1 Variants", w.now())
    w.set_stock(OUT, OUT, OUT, OUT)
    w.clock.sleep(7200)
    check(w)
    w.clock.sleep(1800)
    check(w)
    pending = ApprovalRepo(w.session).list_pending()
    assert len(pending) == 1
    assert sorted(c.variant_id for c in pending[0].changes) == [1, 2, 3, 4]
    notes = [n for n in NotificationRepo(w.session).list(resolved=False)
             if n.kind == "pending_approval"]
    assert len(notes) == 1 and "4 Variants" in notes[0].message


# --- 4. Stale means the same thing everywhere ---------------------------------------


def test_variant_info_uses_the_shortest_interval_among_its_suppliers(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1, interval_min=15)
    other = SupplierRepo(w.session, w.box).create("Supplier B", BASE, w.now(), interval_min=240)
    from app.db.repos.catalog import CatalogRepo, ImportRow
    CatalogRepo(w.session).import_rows([ImportRow("SKU1", other.id, f"{BASE}/other/1", "")])
    info = queries.variant_info(w.session, w.gids[0])
    assert info is not None and info.interval_min == 15


def test_an_order_is_flagged_when_the_dashboards_stale_rule_says_stale(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1, interval_min=15)
    other = SupplierRepo(w.session, w.box).create("Supplier B", BASE, w.now(), interval_min=240)
    from app.db.repos.catalog import CatalogRepo, ImportRow
    CatalogRepo(w.session).import_rows([ImportRow("SKU1", other.id, f"{BASE}/other/1", "")])
    for listing_id in (1, 2):  # last read 60 minutes ago: older than twice 15 minutes
        StateRepo(w.session).save_listing_state(listing_id, ListingState(
            status=StockStatus.IN_STOCK, last_success_at=w.clock.now() - 3600))
    w.shopify.orders = [Order("A", "#A", "2026-11-03T10:00:00Z", (w.gids[0],), False)]
    with w.deps.session_factory() as s:
        handle_poll_orders(w.deps, s, JobRecord(1, "poll_orders", None,
                                                {"since": "2026-11-03T09:00:00Z"}, 0))
    assert [o.order_id for o in OrderRepo(w.session).list_flagged()] == ["A"]


# --- 5. a job stuck running is requeued while the worker is up -----------------------


def test_the_worker_loop_requeues_a_job_left_running_by_a_dead_worker(
    make_world: Callable[..., World],
) -> None:
    w = make_world(variants=1)
    stop = threading.Event()
    thread = threading.Thread(target=serve, args=(w.deps, stop, 30.0, 0.01), daemon=True)
    thread.start()
    try:
        time.sleep(0.3)  # the worker is up and has done its start-up requeue
        stuck = Job(kind="unknown_kind", supplier_id=None, payload={}, state="running",
                    run_after=w.now(), locked_at=w.now() - timedelta(hours=3),
                    created_at=w.now())
        w.session.add(stuck)
        w.session.commit()
        w.clock.sleep(31)  # next tick
        deadline = time.time() + 10
        attempts = 0
        while time.time() < deadline and attempts == 0:
            time.sleep(0.05)
            w.session.expire_all()
            attempts = w.session.scalar(select(Job.attempts).where(Job.id == stuck.id)) or 0
        assert attempts == 1  # it was requeued, claimed again and (being unknown) failed once
    finally:
        stop.set()
        thread.join(timeout=5)
