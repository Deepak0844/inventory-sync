"""Dashboard notifications (ADR 0002). Not responsible for deciding when to raise one."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Notification, Supplier


@dataclass(frozen=True)
class NotificationRecord:
    id: int
    kind: str
    supplier_id: int | None
    supplier_name: str | None
    message: str
    created_at: datetime
    resolved_at: datetime | None
    screenshot_path: str | None


class NotificationRepo:
    """Rows of the `notifications` table."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self, kind: str, supplier_id: int | None, message: str, now: datetime,
        screenshot_path: str | None = None,
    ) -> int:
        """Raise a notification. Returns its id."""
        n = Notification(kind=kind, supplier_id=supplier_id, message=message, created_at=now,
                         screenshot_path=screenshot_path)
        self._s.add(n)
        self._s.commit()
        return n.id

    def list(self, resolved: bool) -> list[NotificationRecord]:
        """Return resolved or unresolved notifications, newest first."""
        col = Notification.resolved_at
        done = col.is_not(None) if resolved else col.is_(None)
        rows = self._s.execute(
            select(Notification, Supplier.name)
            .outerjoin(Supplier, Supplier.id == Notification.supplier_id).where(done)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        ).all()
        return [NotificationRecord(n.id, n.kind, n.supplier_id, name, n.message, n.created_at,
                                   n.resolved_at, n.screenshot_path) for n, name in rows]

    def resolve(self, notification_id: int, now: datetime) -> None:
        """Mark resolved. Resolving again keeps the first time."""
        self._s.execute(update(Notification).where(
            Notification.id == notification_id, Notification.resolved_at.is_(None)
        ).values(resolved_at=now))
        self._s.commit()
