from datetime import UTC, datetime, timedelta

from app.db.repos.history import ChangeRecord
from app.services.overview import sold_out_by_day

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)


def change(variant: int, to_state: str, days_ago: float) -> ChangeRecord:
    return ChangeRecord(NOW - timedelta(days=days_ago), variant, f"S{variant}", None, to_state,
                        "r", "auto")


def counts(changes: list[ChangeRecord], days: int = 3) -> list[int]:
    return [d.count for d in sold_out_by_day(changes, NOW, days)]


def test_each_day_counts_the_variants_sold_out_at_its_end() -> None:
    changes = [change(1, "sold_out", 2.5), change(2, "sold_out", 1.2), change(1, "available", 0.2)]
    assert counts(changes) == [1, 2, 1]


def test_a_variant_sold_out_before_the_window_still_counts() -> None:
    assert counts([change(1, "sold_out", 30)]) == [1, 1, 1]


def test_days_are_dated_oldest_first_and_end_today() -> None:
    days = sold_out_by_day([], NOW, 3)
    assert [d.date.isoformat() for d in days] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert [d.count for d in days] == [0, 0, 0]


def test_today_counts_only_up_to_now() -> None:
    assert counts([change(1, "sold_out", 0.01)])[-1] == 1
    later = ChangeRecord(NOW + timedelta(hours=1), 9, "S9", None, "sold_out", "r", "auto")
    assert counts([later])[-1] == 0


def test_the_last_change_of_a_variant_wins_within_a_day() -> None:
    changes = [change(1, "sold_out", 0.5), change(1, "available", 0.4)]
    assert counts(changes)[-1] == 0
