"""Raising dashboard notifications without repeating one that is still open."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.repos.notifications import NotificationRepo


def notify_once(
    session: Session, kind: str, supplier_id: int | None, message: str, now: datetime
) -> None:
    """Raise a notification unless an unresolved one of the same kind and Supplier exists.

    A problem that lasts (a broken flow, a paused login) is checked every
    interval; this keeps it from filling the dashboard with copies.
    """
    repo = NotificationRepo(session)
    if not any(n.kind == kind and n.supplier_id == supplier_id for n in repo.list(resolved=False)):
        repo.add(kind, supplier_id, message, now)


def replace_notification(
    session: Session, kind: str, supplier_id: int | None, message: str, now: datetime
) -> None:
    """Make the open notification of this kind and Supplier say `message`.

    Used when the facts change while a notification is open (a pending batch grows),
    so the dashboard never shows an outdated count. An open one that already says
    this is left alone.
    """
    repo = NotificationRepo(session)
    open_ones = [n for n in repo.list(resolved=False)
                 if n.kind == kind and n.supplier_id == supplier_id]
    if any(n.message == message for n in open_ones):
        return
    for n in open_ones:
        repo.resolve(n.id, now)
    repo.add(kind, supplier_id, message, now)
