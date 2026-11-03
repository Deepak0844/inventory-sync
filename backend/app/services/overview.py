"""The Overview screen and the shell banner, built from the repositories.

Not responsible for HTTP. Reads only; nothing here changes state.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.counts import Counts
from app.db.repos.history import ChangeRecord, HistoryRepo
from app.db.repos.suppliers import SupplierRepo
from app.services import catalog, suppliers

RECENT_CHANGES = 6
CHART_DAYS = 14


class Change(Protocol):
    """What the chart needs from a change: which Variant, when, and the state it went to."""

    @property
    def variant_id(self) -> int: ...
    @property
    def at(self) -> datetime: ...
    @property
    def to_state(self) -> str: ...


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


def sold_out_by_day(changes: Sequence[Change], now: datetime, days: int) -> list[DayCount]:
    """Count the Variants that were Sold Out at the end of each of the last `days` days.

    Args:
        changes: Inventory changes in any order: those inside the window plus each Variant's
            last change before it. A Variant's latest change at or before the end of a day
            decides its state that day, so one sold out before the window still counts.
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
    """Gather the numbers the Overview screen shows, in a fixed number of queries."""
    counts = Counts(session)
    by_state = counts.variants_by_state()
    first_day = datetime.combine(now.date() - timedelta(days=CHART_DAYS - 1), time.min, now.tzinfo)
    return Overview(
        updated_at=now,
        sold_out=by_state.get("sold_out", 0),
        in_stock=by_state.get("available", 0),
        stale=catalog.count_stale(session, box, now),
        pending=counts.pending_approvals(),
        sold_out_by_day=sold_out_by_day(HistoryRepo(session).chart_changes(first_day), now,
                                        CHART_DAYS),
        suppliers=[
            SupplierHealth(s.id, s.name, suppliers.supplier_health(s, now), s.last_success_at)
            for s in SupplierRepo(session, box).list()
        ],
        recent_changes=HistoryRepo(session).recent_changes(RECENT_CHANGES),
    )


def build_banner(session: Session, box: SecretBox, now: datetime) -> Banner:
    """Gather what the shell shows on every screen: overdue Suppliers and queue counts.

    Polled constantly, so it only counts rows; it never loads the lists.
    """
    counts = Counts(session)
    overdue = [
        RedStripEntry(s.id, s.name, s.last_success_at)
        for s in SupplierRepo(session, box).list()
        if s.last_success_at is not None and suppliers.is_overdue(s, now)
    ]
    return Banner(
        red_strip=overdue,
        approvals=counts.pending_approvals(),
        orders=counts.flagged_orders(),
        notifications=counts.unresolved_notifications(),
    )
