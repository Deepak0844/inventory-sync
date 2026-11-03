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
