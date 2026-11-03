"""Approvals, notifications and flagged orders: the queues the owner works through.

Not responsible for HTTP, or for applying approved changes to Shopify (the worker does
that when it picks up the `apply_approval` job).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.repos.approvals import ApprovalRepo, PendingApproval
from app.db.repos.jobs import JobRepo
from app.db.repos.notifications import NotificationRecord, NotificationRepo
from app.db.repos.orders import FlaggedOrderRecord, OrderRepo


class ApprovalNotFound(Exception):
    """No pending approval has this id (unknown, or already decided)."""


class ScreenshotNotFound(Exception):
    """The notification has no screenshot that is safe to serve."""


@dataclass(frozen=True)
class FlaggedOrderView:
    order_id: str
    name: str
    created_at: datetime
    reasons: list[str]
    variants: list[tuple[str, str]]


def list_approvals(session: Session) -> list[PendingApproval]:
    """Return held change batches still waiting for the owner, oldest first."""
    return ApprovalRepo(session).list_pending()


def approve(session: Session, now: datetime, approval_id: int) -> None:
    """Approve a pending batch and queue its application, exactly once.

    Raises:
        ApprovalNotFound: if unknown or already decided, so a double click queues nothing.
    """
    batch = next((a for a in ApprovalRepo(session).list_pending() if a.id == approval_id), None)
    if batch is None or ApprovalRepo(session).decide(approval_id, True, now) is None:
        raise ApprovalNotFound(approval_id)
    JobRepo(session).enqueue(
        "apply_approval", batch.supplier_id, {"approval_id": approval_id}, run_after=now, now=now
    )


def reject(session: Session, now: datetime, approval_id: int) -> None:
    """Discard a pending batch; nothing reaches Shopify.

    Raises:
        ApprovalNotFound: if unknown or already decided.
    """
    if ApprovalRepo(session).decide(approval_id, False, now) is None:
        raise ApprovalNotFound(approval_id)


def list_notifications(session: Session, resolved: bool) -> list[NotificationRecord]:
    """Return resolved or unresolved notifications, newest first."""
    return NotificationRepo(session).list(resolved)


def resolve_notification(session: Session, now: datetime, notification_id: int) -> None:
    """Mark a notification resolved. Idempotent; an unknown id changes nothing."""
    NotificationRepo(session).resolve(notification_id, now)


def screenshot_path(session: Session, screenshot_dir: Path, notification_id: int) -> Path:
    """Return the screenshot file for a notification, only if it lies inside `screenshot_dir`.

    The stored path is resolved first, so `..` segments and symlinks cannot reach other files.

    Raises:
        ScreenshotNotFound: if there is none, it is outside the folder, or the file is gone.
    """
    record = NotificationRepo(session).get(notification_id)
    if record is None or record.screenshot_path is None:
        raise ScreenshotNotFound(notification_id)
    path = Path(record.screenshot_path).resolve()
    if not path.is_relative_to(screenshot_dir.resolve()) or not path.is_file():
        raise ScreenshotNotFound(notification_id)
    return path


def flagged_orders(session: Session) -> list[FlaggedOrderView]:
    """Return orders flagged "verify with Supplier", newest first, with why."""
    return [_order_view(o) for o in OrderRepo(session).list_flagged()]


def _order_view(order: FlaggedOrderRecord) -> FlaggedOrderView:
    reasons = list(dict.fromkeys(line.reason for line in order.lines))
    if order.lines_truncated:
        reasons.append("lines_truncated")
    return FlaggedOrderView(order.order_id, order.name, order.created_at, reasons,
                            [(line.sku, line.reason) for line in order.lines])
