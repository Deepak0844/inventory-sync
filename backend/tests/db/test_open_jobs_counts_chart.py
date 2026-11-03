from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.repos.approvals import ApprovalRepo
from app.db.repos.catalog import CatalogRepo
from app.db.repos.counts import Counts
from app.db.repos.history import HistoryRepo
from app.db.repos.jobs import JobRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import OrderRepo
from app.db.repos.states import StateRepo
from tests.db.helpers import NOW, make_supplier

# --- has_open_job ---------------------------------------------------------------------


def test_a_queued_job_is_open(db_session: Session) -> None:
    sid = make_supplier(db_session)
    jobs = JobRepo(db_session)
    jobs.enqueue("check_supplier", sid, {}, NOW, NOW)
    assert jobs.has_open_job("check_supplier", sid)


def test_a_running_job_is_open(db_session: Session) -> None:
    sid = make_supplier(db_session)
    jobs = JobRepo(db_session)
    jobs.enqueue("check_supplier", sid, {}, NOW, NOW)
    assert jobs.claim_next(NOW) is not None
    assert jobs.has_open_job("check_supplier", sid)


def test_a_finished_job_is_not_open(db_session: Session) -> None:
    sid = make_supplier(db_session)
    jobs = JobRepo(db_session)
    job_id = jobs.enqueue("check_supplier", sid, {}, NOW, NOW)
    jobs.complete(job_id)
    assert not jobs.has_open_job("check_supplier", sid)


def test_open_means_the_same_kind_and_the_same_supplier(db_session: Session) -> None:
    a, b = make_supplier(db_session, "A"), make_supplier(db_session, "B")
    jobs = JobRepo(db_session)
    jobs.enqueue("check_supplier", a, {}, NOW, NOW)
    assert not jobs.has_open_job("login", a)
    assert not jobs.has_open_job("check_supplier", b)
    assert not jobs.has_open_job("check_supplier", None)


def test_a_job_without_a_supplier_is_found_with_none(db_session: Session) -> None:
    jobs = JobRepo(db_session)
    jobs.enqueue("poll_orders", None, {}, NOW, NOW)
    assert jobs.has_open_job("poll_orders", None)


def test_later_than_only_counts_jobs_set_to_run_after_that_time(db_session: Session) -> None:
    sid = make_supplier(db_session)
    jobs = JobRepo(db_session)
    jobs.enqueue("check_supplier", sid, {}, NOW + timedelta(minutes=30), NOW)
    assert jobs.has_open_job("check_supplier", sid, later_than=NOW)
    assert not jobs.has_open_job("check_supplier", sid, later_than=NOW + timedelta(hours=1))


# --- cheap counts for the banner and overview -------------------------------------------


def test_counts_of_pending_approvals_flagged_orders_and_open_notifications(
    db_session: Session,
) -> None:
    sid = make_supplier(db_session)
    notes = NotificationRepo(db_session)
    first = notes.add("flow_failure", sid, "one", NOW)
    notes.add("flow_failure", sid, "two", NOW)
    notes.resolve(first, NOW)
    counts = Counts(db_session)
    assert counts.unresolved_notifications() == 1
    assert counts.pending_approvals() == 0
    assert counts.flagged_orders() == 0
    ApprovalRepo(db_session).create(sid, [], NOW)
    OrderRepo(db_session).flag("gid://o/1", "#1", NOW, [], False, NOW)
    assert counts.pending_approvals() == 1
    assert counts.flagged_orders() == 1


def test_variant_state_counts(db_session: Session) -> None:
    catalog, states = CatalogRepo(db_session), StateRepo(db_session)
    for sku, state in (("A", "sold_out"), ("B", "sold_out"), ("C", "available")):
        vid = catalog.upsert_variant(f"gid://v/{sku}", sku, sku)
        states.save_variant_state(vid, state, NOW, None)
    catalog.upsert_variant("gid://v/D", "D", "D")  # not managed yet
    assert Counts(db_session).variants_by_state() == {"sold_out": 2, "available": 1}


# --- the Sold Out chart reads a bounded slice ------------------------------------------


def test_chart_changes_are_the_window_plus_each_variants_state_before_it(
    db_session: Session,
) -> None:
    catalog, history = CatalogRepo(db_session), HistoryRepo(db_session)
    v1, v2, v3 = (catalog.upsert_variant(f"gid://v/{i}", f"S{i}", f"S{i}") for i in (1, 2, 3))
    since = NOW - timedelta(days=13)
    history.record_change(v1, None, "sold_out", "r", "auto", NOW - timedelta(days=40))
    history.record_change(v1, "sold_out", "available", "r", "auto", NOW - timedelta(days=30))
    history.record_change(v2, None, "sold_out", "r", "auto", NOW - timedelta(days=20))
    history.record_change(v3, None, "sold_out", "r", "auto", NOW - timedelta(days=3))
    rows = history.chart_changes(since)
    assert sorted((c.variant_id, c.to_state) for c in rows) == [
        (v1, "available"), (v2, "sold_out"), (v3, "sold_out")]
