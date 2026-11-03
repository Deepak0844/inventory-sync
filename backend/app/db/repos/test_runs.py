"""Test runs of the flow builder. Not responsible for running them (`app.worker.test_run`)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import FlowTestRun

OPEN_STATES = ("queued", "running", "waiting_for_code")


@dataclass(frozen=True)
class FlowTestRunRecord:
    """A Test run as stored. `steps` and the JSON fields follow docs/api.md."""

    id: int
    supplier_id: int
    state: str
    mode: str
    request: dict[str, Any]
    steps: list[dict[str, Any]]
    snapshot: dict[str, Any] | None
    reading: dict[str, Any] | None
    login_result: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class FlowTestRunRepo:
    """Rows of the `test_runs` table. Each method is one transaction."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, supplier_id: int, mode: str, request: dict[str, Any], now: datetime) -> int:
        """Add a queued run. Returns its id."""
        run = FlowTestRun(supplier_id=supplier_id, mode=mode, request=request, steps=[],
                          created_at=now)
        self._s.add(run)
        self._s.commit()
        return run.id

    def get(self, run_id: int) -> FlowTestRunRecord | None:
        """Return one run, or None."""
        row = self._s.get(FlowTestRun, run_id)
        return None if row is None else _record(row)

    def open_for_supplier(self, supplier_id: int) -> FlowTestRunRecord | None:
        """Return the Supplier's run that has not finished, if any (newest first)."""
        row = self._s.scalars(
            select(FlowTestRun)
            .where(FlowTestRun.supplier_id == supplier_id, FlowTestRun.state.in_(OPEN_STATES))
            .order_by(FlowTestRun.id.desc()).limit(1)
        ).first()
        return None if row is None else _record(row)

    def start(self, run_id: int) -> None:
        """Mark a run running and clear its steps, so a run restarted after a crash is clean."""
        row = self._s.get(FlowTestRun, run_id)
        if row is not None:
            row.state, row.steps = "running", []
            self._s.commit()

    def set_state(self, run_id: int, state: str) -> None:
        """Move a run to `state` (queued, running or waiting_for_code)."""
        row = self._s.get(FlowTestRun, run_id)
        if row is not None:
            row.state = state
            self._s.commit()

    def add_step(self, run_id: int, step: dict[str, Any]) -> None:
        """Append one step so a polling dashboard sees progress."""
        row = self._s.get(FlowTestRun, run_id)
        if row is not None:
            row.steps = [*row.steps, step]  # reassigned: JSON columns do not track appends
            self._s.commit()

    def finish(
        self, run_id: int, state: str, now: datetime, *, snapshot: dict[str, Any] | None = None,
        reading: dict[str, Any] | None = None, login_result: str | None = None,
        error: str | None = None,
    ) -> None:
        """Close a run as `done` or `failed` with what it found."""
        row = self._s.get(FlowTestRun, run_id)
        if row is not None:
            row.state, row.finished_at = state, now
            row.snapshot, row.reading = snapshot, reading
            row.login_result, row.error = login_result, error
            self._s.commit()

    def delete_older_than(self, cutoff: datetime) -> list[int]:
        """Delete runs created before `cutoff`. Returns their ids so the caller can remove files."""
        ids = list(self._s.scalars(select(FlowTestRun.id).where(FlowTestRun.created_at < cutoff)))
        if ids:
            self._s.execute(delete(FlowTestRun).where(FlowTestRun.id.in_(ids)))
            self._s.commit()
        return ids


def _record(row: FlowTestRun) -> FlowTestRunRecord:
    return FlowTestRunRecord(
        row.id, row.supplier_id, row.state, row.mode, dict(row.request), list(row.steps),
        row.snapshot, row.reading, row.login_result, row.error, row.created_at, row.finished_at)
