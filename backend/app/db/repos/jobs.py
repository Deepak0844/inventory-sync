"""The Postgres job queue (ADR 0001): enqueue, claim with SKIP LOCKED, retry.

Not responsible for what a job does; the worker interprets `kind` and `payload`.
Each method is one transaction, so a claim is visible to other workers at once.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Job


@dataclass(frozen=True)
class JobRecord:
    """A claimed job."""

    id: int
    kind: str
    supplier_id: int | None
    payload: dict[str, Any]
    attempts: int


@dataclass(frozen=True)
class JobStatus:
    """The public state and progress payload of one queued job."""

    id: int
    state: str
    payload: dict[str, Any]
    last_error: str | None


class JobRepo:
    """Queue operations on the `jobs` table."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def enqueue(
        self, kind: str, supplier_id: int | None, payload: dict[str, Any],
        run_after: datetime, now: datetime,
    ) -> int:
        """Add a job that may be claimed from `run_after`. Returns its id."""
        job = Job(kind=kind, supplier_id=supplier_id, payload=payload, run_after=run_after,
                  created_at=now)
        self._s.add(job)
        self._s.commit()
        return job.id

    def claim_next(self, now: datetime, kinds: set[str] | None = None) -> JobRecord | None:
        """Claim the oldest due job, or return None.

        `FOR UPDATE SKIP LOCKED` lets many workers poll at once without ever
        receiving the same job.
        """
        query = select(Job).where(Job.state == "queued", Job.run_after <= now)
        if kinds is not None:
            query = query.where(Job.kind.in_(kinds))
        job = self._s.execute(
            query
            .order_by(Job.run_after, Job.id).limit(1).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if job is None:
            self._s.rollback()
            return None
        job.state, job.locked_at = "running", now
        record = JobRecord(job.id, job.kind, job.supplier_id, dict(job.payload), job.attempts)
        self._s.commit()
        return record

    def latest(self, kind: str, supplier_id: int) -> JobStatus | None:
        """Return the newest job of this kind for a Supplier."""
        job = self._s.scalar(
            select(Job).where(Job.kind == kind, Job.supplier_id == supplier_id)
            .order_by(Job.id.desc()).limit(1)
        )
        return None if job is None else JobStatus(
            job.id, job.state, dict(job.payload), job.last_error
        )

    def set_result(self, job_id: int, state: str, **payload: Any) -> None:
        """Update manual progress, completing terminal states."""
        job = self._s.get(Job, job_id)
        if job is None:
            return
        job.payload = {**dict(job.payload), "manual_state": state, **payload}
        if state in {"succeeded", "failed", "expired", "cancelled"}:
            job.state, job.locked_at = "done", None
        self._s.commit()

    def complete(self, job_id: int) -> None:
        """Mark a job done."""
        self._s.execute(update(Job).where(Job.id == job_id).values(state="done", locked_at=None))
        self._s.commit()

    def fail(
        self, job_id: int, now: datetime, error: str, retry_after_s: float, max_attempts: int
    ) -> None:
        """Record a failure: retry after `retry_after_s`, or give up after `max_attempts`."""
        job = self._s.get(Job, job_id)
        if job is None:
            return
        job.attempts += 1
        job.last_error = error
        job.locked_at = None
        if job.attempts >= max_attempts:
            job.state = "failed"
        else:
            job.state, job.run_after = "queued", now + timedelta(seconds=retry_after_s)
        self._s.commit()

    def requeue_stale(self, now: datetime, older_than_s: float) -> int:
        """Put jobs back that a dead worker left running. Returns how many."""
        result = self._s.execute(
            update(Job).where(Job.state == "running",
                              Job.locked_at < now - timedelta(seconds=older_than_s))
            .values(state="queued", locked_at=None)
        )
        self._s.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    def has_open_job(
        self, kind: str, supplier_id: int | None, later_than: datetime | None = None
    ) -> bool:
        """Whether a queued or running job of this kind exists for the Supplier.

        Args:
            kind: The job kind.
            supplier_id: The Supplier, or None for a job that belongs to no Supplier.
            later_than: If given, only count jobs set to run after this time.
        """
        query = select(Job.id).where(
            Job.kind == kind,
            Job.supplier_id.is_(None) if supplier_id is None else Job.supplier_id == supplier_id,
            Job.state.in_(["queued", "running"]))
        if later_than is not None:
            query = query.where(Job.run_after > later_than)
        return self._s.scalar(query.limit(1)) is not None
