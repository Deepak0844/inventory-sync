"""The Overview screen and the shell banner, built from the repositories.

Not responsible for HTTP. Reads only; nothing here changes state.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.approvals import ApprovalRepo
from app.db.repos.catalog import CatalogRepo
from app.db.repos.history import ChangeRecord, HistoryRepo
from app.db.repos.notifications import NotificationRepo
from app.db.repos.orders import OrderRepo
from app.db.repos.suppliers import SupplierRepo
from app.services import catalog, suppliers

RECENT_CHANGES = 6
CHART_DAYS = 14


@dataclass(frozen=True)
class DayCount:
    date: date
    count: int


@dataclass(frozen=True)
class SupplierHealth:
    id: int
    name: str
    health: str
    last_success_at: datetime | None


@dataclass(frozen=True)
class Overview:
    updated_at: datetime
    sold_out: int
    in_stock: int
    stale: int
    pending: int
    sold_out_by_day: list[DayCount]
    suppliers: list[SupplierHealth]
    recent_changes: list[ChangeRecord]


@dataclass(frozen=True)
class RedStripEntry:
    supplier_id: int
    supplier_name: str
    last_success_at: datetime


@dataclass(frozen=True)
class Banner:
    red_strip: list[RedStripEntry]
    approvals: int
    orders: int
    notifications: int


def sold_out_by_day(changes: list[ChangeRecord], now: datetime, days: int) -> list[DayCount]:
    """Count the Variants that were Sold Out at the end of each of the last `days` days.

    Args:
        changes: Every inventory change, oldest first. A Variant's latest change at or before
            the end of a day decides its state that day, so one sold out before the window
            still counts.
        now: Today's count stops at this moment.
        days: How many days to return, ending today (UTC).

    Returns:
        One `DayCount` per day, oldest first.
    """
    today = now.date()
    result: list[DayCount] = []
    state: dict[int, str] = {}
    pending = iter(sorted(changes, key=lambda c: c.at))
    upcoming = next(pending, None)
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        midnight = datetime.combine(day + timedelta(days=1), time.min, now.tzinfo)
        end = now if offset == 0 else midnight
        while upcoming is not None and upcoming.at <= end:
            state[upcoming.variant_id] = upcoming.to_state
            upcoming = next(pending, None)
        result.append(DayCount(day, sum(1 for s in state.values() if s == "sold_out")))
    return result


def build_overview(session: Session, box: SecretBox, now: datetime) -> Overview:
    """Gather the numbers the Overview screen shows."""
    catalog_repo = CatalogRepo(session)
    stale = catalog.list_variants(session, box, now, None, True, None, None, 1).total
    return Overview(
        updated_at=now,
        sold_out=catalog_repo.list_variants(state="sold_out", limit=1).total,
        in_stock=catalog_repo.list_variants(state="available", limit=1).total,
        stale=stale,
        pending=len(ApprovalRepo(session).list_pending()),
        sold_out_by_day=sold_out_by_day(HistoryRepo(session).all_changes(), now, CHART_DAYS),
        suppliers=[
            SupplierHealth(s.id, s.name, suppliers.supplier_health(s, now), s.last_success_at)
            for s in SupplierRepo(session, box).list()
        ],
        recent_changes=HistoryRepo(session).recent_changes(RECENT_CHANGES),
    )


def build_banner(session: Session, box: SecretBox, now: datetime) -> Banner:
    """Gather what the shell shows on every screen: overdue Suppliers and queue counts."""
    overdue = [
        RedStripEntry(s.id, s.name, s.last_success_at)
        for s in SupplierRepo(session, box).list()
        if s.last_success_at is not None and suppliers.is_overdue(s, now)
    ]
    return Banner(
        red_strip=overdue,
        approvals=len(ApprovalRepo(session).list_pending()),
        orders=len(OrderRepo(session).list_flagged()),
        notifications=len(NotificationRepo(session).list(resolved=False)),
    )
