"""One scheduler tick: enqueue the jobs that are due, never twice.

Stateless between ticks: what already ran or is queued is read from the
database, so a restarted worker neither forgets nor repeats work.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.models import Job, Notification, Run
from app.db.repos.jobs import JobRepo
from app.db.repos.settings import SettingsRepo
from app.db.repos.suppliers import SupplierRepo
from app.scheduler.due import SupplierSchedule, due_suppliers

VARIANT_SYNC_EVERY = timedelta(hours=1)
SUMMARY_EVERY = timedelta(hours=24)


def tick(session: Session, box: SecretBox, now: datetime) -> None:
    """Enqueue due `check_supplier`, `poll_orders`, `sync_variants` and `daily_summary` jobs."""
    jobs = JobRepo(session)
    settings = SettingsRepo(session, box).get()
    last_runs = dict(session.execute(
        select(Run.supplier_id, func.max(Run.started_at)).where(Run.kind == "check")
        .group_by(Run.supplier_id)).tuples().all())
    schedules = [
        SupplierSchedule(s.id, s.interval_min, s.paused, s.waiting_for_code_until,
                         last_runs.get(s.id))
        for s in SupplierRepo(session, box).list()
    ]
    for supplier_id in due_suppliers(schedules, now):
        if not has_open_job(session, "check_supplier", supplier_id):
            jobs.enqueue("check_supplier", supplier_id, {}, now, now)
    if settings.shop_domain:
        every = timedelta(minutes=settings.order_poll_min)
        if _job_due(session, "poll_orders", now, every):
            # Twice the poll interval back, so a slow poll cannot miss an order (the
            # filter is inclusive and orders are de-duplicated by id).
            since = (now - 2 * every).strftime("%Y-%m-%dT%H:%M:%SZ")
            jobs.enqueue("poll_orders", None, {"since": since}, now, now)
        if _job_due(session, "sync_variants", now, VARIANT_SYNC_EVERY):
            jobs.enqueue("sync_variants", None, {}, now, now)
    last_summary = session.scalar(select(func.max(Notification.created_at)).where(
        Notification.kind == "daily_summary"))
    if (last_summary is None or now - last_summary >= SUMMARY_EVERY) and not has_open_job(
            session, "daily_summary", None):
        jobs.enqueue("daily_summary", None, {}, now, now)


def has_open_job(
    session: Session, kind: str, supplier_id: int | None, later_than: datetime | None = None
) -> bool:
    """Whether a queued or running job exists, optionally only one set to run after a time."""
    query = select(Job.id).where(
        Job.kind == kind,
        Job.supplier_id.is_(None) if supplier_id is None else Job.supplier_id == supplier_id,
        Job.state.in_(["queued", "running"]))
    if later_than is not None:
        query = query.where(Job.run_after > later_than)
    return session.scalar(query.limit(1)) is not None


def _job_due(session: Session, kind: str, now: datetime, every: timedelta) -> bool:
    """True when no job of this kind is open and the latest one is at least `every` old."""
    if has_open_job(session, kind, None):
        return False
    latest = session.scalar(select(func.max(Job.created_at)).where(Job.kind == kind))
    return latest is None or now - latest >= every
