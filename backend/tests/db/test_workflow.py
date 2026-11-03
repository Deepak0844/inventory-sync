from sqlalchemy.orm import Session

from app.db.repos.approvals import ApprovalRepo, HeldChange
from app.db.repos.catalog import CatalogRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import FlaggedLine, OrderRepo
from app.db.repos.runs import RunRepo
from tests.db.helpers import NOW, later, make_supplier


def test_notification_resolve(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    repo = NotificationRepo(db_session)
    n = repo.add("flow_failure", supplier, "Selector not found", NOW, "shots/a.png")
    keep = repo.add("needs_code", supplier, "Waiting for a code", later(1))
    assert {x.id for x in repo.list(resolved=False)} == {n, keep}
    repo.resolve(n, later(5))
    assert [x.id for x in repo.list(resolved=False)] == [keep]
    done = repo.list(resolved=True)
    assert [x.id for x in done] == [n] and done[0].supplier_name == "Supplier A"
    assert done[0].screenshot_path == "shots/a.png" and done[0].resolved_at == later(5)


def test_resolving_twice_keeps_the_first_time(db_session: Session) -> None:
    repo = NotificationRepo(db_session)
    n = repo.add("daily_summary", None, "All quiet", NOW)
    repo.resolve(n, later(5))
    repo.resolve(n, later(50))
    assert repo.list(resolved=True)[0].resolved_at == later(5)


def approval_with_one_change(db_session: Session) -> int:
    catalog = CatalogRepo(db_session)
    variant = catalog.upsert_variant("gid://v/1", "SKU-1", "T")
    supplier = make_supplier(db_session)
    return ApprovalRepo(db_session).create(
        supplier, [HeldChange(variant, "available", "sold_out", 0)], NOW)


def test_pending_approval_lists_its_changes(db_session: Session) -> None:
    approval_id = approval_with_one_change(db_session)
    pending = ApprovalRepo(db_session).list_pending()
    assert [p.id for p in pending] == [approval_id]
    assert (pending[0].supplier_name, pending[0].changes[0].sku) == ("Supplier A", "SKU-1")


def test_approve_returns_the_changes_once(db_session: Session) -> None:
    approval_id = approval_with_one_change(db_session)
    repo = ApprovalRepo(db_session)
    first = repo.decide(approval_id, approved=True, now=later(1))
    assert first is not None and [c.to_state for c in first] == ["sold_out"]
    assert repo.decide(approval_id, approved=True, now=later(2)) is None
    assert repo.decide(approval_id, approved=False, now=later(3)) is None
    assert repo.list_pending() == []


def test_reject_discards_and_cannot_be_approved_later(db_session: Session) -> None:
    approval_id = approval_with_one_change(db_session)
    repo = ApprovalRepo(db_session)
    assert repo.decide(approval_id, approved=False, now=later(1)) == []
    assert repo.decide(approval_id, approved=True, now=later(2)) is None


def test_unknown_approval_is_none(db_session: Session) -> None:
    assert ApprovalRepo(db_session).decide(999, approved=True, now=NOW) is None


def test_flagging_the_same_order_twice_keeps_one(db_session: Session) -> None:
    repo = OrderRepo(db_session)
    lines = [FlaggedLine("SKU-1", "stale")]
    assert repo.flag("gid://o/1", "#1001", NOW, lines, False, later(5)) is True
    assert repo.flag("gid://o/1", "#1001", NOW, lines, False, later(9)) is False
    flagged = repo.list_flagged()
    assert len(flagged) == 1 and flagged[0].lines[0].reason == "stale"


def test_runs_start_and_finish(db_session: Session) -> None:
    supplier = make_supplier(db_session)
    runs = RunRepo(db_session)
    run_id = runs.start(supplier, "check", NOW)
    assert runs.list_for_supplier(supplier)[0].state == "running"
    runs.finish(run_id, "ok", "12 listings read", later(30))
    done = runs.list_for_supplier(supplier)[0]
    assert (done.state, done.summary, done.finished_at) == ("ok", "12 listings read", later(30))
