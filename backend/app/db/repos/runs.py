"""Run history per Supplier. Not responsible for deciding what a run did."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Run


@dataclass(frozen=True)
class RunRecord:
    id: int
    kind: str
    state: str
    started_at: datetime
    finished_at: datetime | None
    summary: str


class RunRepo:
    """Rows of the `runs` table."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def start(self, supplier_id: int, kind: str, now: datetime) -> int:
        """Open a run in state "running". Returns its id."""
        run = Run(supplier_id=supplier_id, kind=kind, state="running", started_at=now)
        self._s.add(run)
        self._s.commit()
        return run.id

    def finish(self, run_id: int, state: str, summary: str, now: datetime) -> None:
        """Close a run with its final state and a one-line summary."""
        run = self._s.get(Run, run_id)
        if run is not None:
            run.state, run.summary, run.finished_at = state, summary, now
            self._s.commit()

    def list_for_supplier(self, supplier_id: int, limit: int = 50) -> list[RunRecord]:
        """Return a Supplier's runs, newest first."""
        rows = self._s.scalars(select(Run).where(Run.supplier_id == supplier_id)
                               .order_by(Run.started_at.desc(), Run.id.desc()).limit(limit))
        return [RunRecord(r.id, r.kind, r.state, r.started_at, r.finished_at, r.summary)
                for r in rows]
