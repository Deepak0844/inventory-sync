"""The `daily_summary` job: one notification with the numbers the owner checks each morning.

It also deletes Test runs (and their screenshots) older than a week.
"""

import shutil
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InventoryChange, Notification, VariantStateRow
from app.db.repos.approvals import ApprovalRepo
from app.db.repos.jobs import JobRecord
from app.db.repos.notifications import NotificationRepo
from app.db.repos.test_runs import FlowTestRunRepo
from app.worker.deps import Deps


def handle_daily_summary(deps: Deps, session: Session, job: JobRecord) -> None:
    """Raise a `daily_summary` notification: Sold Out, waiting for approval, open, changed."""
    now = deps.now()
    _delete_old_test_runs(deps, session, now)
    sold_out = session.scalar(select(func.count()).select_from(VariantStateRow).where(
        VariantStateRow.state == "sold_out"))
    open_issues = session.scalar(select(func.count()).select_from(Notification).where(
        Notification.resolved_at.is_(None), Notification.kind != "daily_summary"))
    changes = session.scalar(select(func.count()).select_from(InventoryChange).where(
        InventoryChange.at >= now - timedelta(hours=24)))
    waiting = len(ApprovalRepo(session).list_pending())
    NotificationRepo(session).add(
        "daily_summary", None,
        f"{sold_out} sold out, {waiting} waiting for approval, {open_issues} open "
        f"notifications, {changes} change(s) in the last 24 hours.", now)


TEST_RUN_KEEP = timedelta(days=7)


def _delete_old_test_runs(deps: Deps, session: Session, now: datetime) -> None:
    """Drop Test runs older than a week, with their files; a missing folder is fine."""
    for run_id in FlowTestRunRepo(session).delete_older_than(now - TEST_RUN_KEEP):
        shutil.rmtree(deps.data_dir / "test-runs" / str(run_id), ignore_errors=True)
