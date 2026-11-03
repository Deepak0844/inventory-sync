from datetime import UTC, datetime, timedelta

import pytest

from app.db.repos.suppliers import SupplierRecord
from app.services.suppliers import is_overdue, supplier_health

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def supplier(**over: object) -> SupplierRecord:
    base: dict[str, object] = dict(
        id=1, name="A", site_url="https://a.example", stock_source="scrape", interval_min=120,
        out_confirm_reads=2, in_confirm_reads=1, confirm_gap_min=30, removed_as_unknown=False,
        max_quantity=100, two_fa_methods=["ui_code"], code_window_min=10, username=None,
        has_password=False, has_flow=False, paused=False, pause_reason=None, blocked=False,
        failed_login_attempts=0, last_success_at=NOW - timedelta(minutes=30),
        waiting_for_code_until=None, session_saved_at=None,
    )
    return SupplierRecord(**{**base, **over})  # type: ignore[arg-type]


def test_a_recently_checked_supplier_is_healthy() -> None:
    assert supplier_health(supplier(), NOW) == "healthy"


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"paused": True}, "paused"),
        ({"blocked": True}, "blocked"),
        ({"waiting_for_code_until": NOW + timedelta(minutes=5)}, "needs_code"),
        ({"last_success_at": NOW - timedelta(minutes=241)}, "stale"),
        ({"last_success_at": None}, "stale"),
    ],
)
def test_health_states(over: dict[str, object], expected: str) -> None:
    assert supplier_health(supplier(**over), NOW) == expected


def test_a_code_prompt_that_has_expired_is_not_needs_code() -> None:
    expired = supplier(waiting_for_code_until=NOW - timedelta(seconds=1))
    assert supplier_health(expired, NOW) == "healthy"


def test_paused_beats_needs_code_beats_blocked_beats_stale() -> None:
    both = supplier(paused=True, blocked=True, last_success_at=None,
                    waiting_for_code_until=NOW + timedelta(minutes=1))
    assert supplier_health(both, NOW) == "paused"
    no_pause = supplier(blocked=True, last_success_at=None,
                        waiting_for_code_until=NOW + timedelta(minutes=1))
    assert supplier_health(no_pause, NOW) == "needs_code"
    assert supplier_health(supplier(blocked=True, last_success_at=None), NOW) == "blocked"


def test_exactly_twice_the_interval_is_not_yet_overdue() -> None:
    assert not is_overdue(supplier(last_success_at=NOW - timedelta(minutes=240)), NOW)
    assert is_overdue(supplier(last_success_at=NOW - timedelta(minutes=241)), NOW)


def test_a_supplier_never_checked_is_not_overdue() -> None:
    assert not is_overdue(supplier(last_success_at=None), NOW)
