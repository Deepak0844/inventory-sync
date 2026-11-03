from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox, generate_key
from app.db.models import Job
from app.db.repos.jobs import JobRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.runs import RunRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.suppliers import SupplierRepo
from app.scheduler.tick import tick

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
BOX = SecretBox(generate_key())


def queued(session: Session, summary: bool = False) -> list[tuple[str, int | None]]:
    rows = session.scalars(select(Job).where(Job.state.in_(["queued", "running"])).order_by(Job.id))
    return [(j.kind, j.supplier_id) for j in rows if summary or j.kind != "daily_summary"]


def supplier(session: Session, **fields: object) -> int:
    return SupplierRepo(session, BOX).create("A", "https://a.test", NOW, **fields).id


def test_a_due_supplier_gets_one_check_job(db_session: Session) -> None:
    sid = supplier(db_session)
    tick(db_session, BOX, NOW)
    tick(db_session, BOX, NOW)
    assert queued(db_session) == [("check_supplier", sid)]


def test_a_supplier_checked_recently_gets_no_job(db_session: Session) -> None:
    sid = supplier(db_session)
    run = RunRepo(db_session).start(sid, "check", NOW - timedelta(minutes=10))
    RunRepo(db_session).finish(run, "ok", "", NOW - timedelta(minutes=9))
    tick(db_session, BOX, NOW)
    assert queued(db_session) == []


def test_a_paused_supplier_gets_no_job(db_session: Session) -> None:
    supplier(db_session, paused=True)
    tick(db_session, BOX, NOW)
    assert queued(db_session) == []


def test_variant_sync_is_hourly_and_not_duplicated(db_session: Session) -> None:
    SettingsRepo(db_session, BOX).update(shop_domain="s.myshopify.com")
    tick(db_session, BOX, NOW)
    assert ("sync_variants", None) in queued(db_session)
    tick(db_session, BOX, NOW + timedelta(minutes=30))
    assert queued(db_session).count(("sync_variants", None)) == 1


def test_variant_sync_runs_again_after_an_hour(db_session: Session) -> None:
    SettingsRepo(db_session, BOX).update(shop_domain="s.myshopify.com")
    tick(db_session, BOX, NOW)
    job = JobRepo(db_session).claim_next(NOW)
    assert job is not None
    JobRepo(db_session).complete(job.id)
    tick(db_session, BOX, NOW + timedelta(minutes=61))
    assert ("sync_variants", None) in queued(db_session)


def test_order_polling_waits_for_a_shop_and_carries_an_overlapping_since(
    db_session: Session,
) -> None:
    tick(db_session, BOX, NOW)
    assert ("poll_orders", None) not in queued(db_session)
    SettingsRepo(db_session, BOX).update(shop_domain="s.myshopify.com", order_poll_min=5)
    tick(db_session, BOX, NOW)
    job = db_session.scalars(select(Job).where(Job.kind == "poll_orders")).one()
    assert job.payload["since"] == "2026-11-03T11:50:00Z"  # twice the poll interval back


def test_daily_summary_once_a_day(db_session: Session) -> None:
    tick(db_session, BOX, NOW)
    assert ("daily_summary", None) in queued(db_session, True)
    NotificationRepo(db_session).add("daily_summary", None, "x", NOW)
    job = JobRepo(db_session).claim_next(NOW)
    assert job is not None
    JobRepo(db_session).complete(job.id)
    tick(db_session, BOX, NOW + timedelta(hours=5))
    assert queued(db_session, True).count(("daily_summary", None)) == 0
    tick(db_session, BOX, NOW + timedelta(hours=25))
    assert ("daily_summary", None) in queued(db_session, True)
