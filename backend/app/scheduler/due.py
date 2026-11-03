"""Which Suppliers are due for a check. Pure; not responsible for enqueueing."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SupplierSchedule:
    """What the schedule needs to know about one Supplier."""

    id: int
    interval_min: int
    paused: bool
    waiting_until: datetime | None
    last_run_at: datetime | None


def due_suppliers(suppliers: Sequence[SupplierSchedule], now: datetime) -> list[int]:
    """Return the ids of Suppliers whose check interval has elapsed.

    A paused Supplier, or one still waiting for a Login Code, is never due: a
    check would only ask for another code.
    """
    return [
        s.id for s in suppliers
        if not s.paused
        and not (s.waiting_until and s.waiting_until > now)
        and (s.last_run_at is None or now - s.last_run_at >= timedelta(minutes=s.interval_min))
    ]
