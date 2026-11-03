from datetime import UTC, datetime, timedelta

from app.scheduler.due import SupplierSchedule, due_suppliers

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def sched(id: int = 1, interval_min: int = 120, paused: bool = False,
          waiting_until: datetime | None = None,
          last_run_at: datetime | None = None) -> SupplierSchedule:
    return SupplierSchedule(id, interval_min, paused, waiting_until, last_run_at)


def test_a_supplier_never_checked_is_due() -> None:
    assert due_suppliers([sched()], NOW) == [1]


def test_due_once_the_interval_has_elapsed() -> None:
    assert due_suppliers([sched(last_run_at=NOW - timedelta(minutes=120))], NOW) == [1]


def test_not_due_before_the_interval() -> None:
    assert due_suppliers([sched(last_run_at=NOW - timedelta(minutes=119))], NOW) == []


def test_a_paused_supplier_is_never_due() -> None:
    assert due_suppliers([sched(paused=True)], NOW) == []


def test_a_supplier_waiting_for_a_code_is_not_due() -> None:
    assert due_suppliers([sched(waiting_until=NOW + timedelta(minutes=3))], NOW) == []


def test_an_expired_code_wait_does_not_block() -> None:
    assert due_suppliers([sched(waiting_until=NOW - timedelta(minutes=1))], NOW) == [1]


def test_each_supplier_uses_its_own_interval() -> None:
    last = NOW - timedelta(minutes=90)
    suppliers = [sched(1, interval_min=60, last_run_at=last), sched(2, 240, last_run_at=last)]
    assert due_suppliers(suppliers, NOW) == [1]
