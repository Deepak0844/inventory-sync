"""Suppliers: health, CRUD, credentials, flows and the actions the worker carries out.

Not responsible for HTTP. The worker does the actual login and checks; the actions
here only queue a job for it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.catalog import CatalogRepo
from app.db.repos.jobs import JobRepo
from app.db.repos.runs import RunRecord, RunRepo
from app.db.repos.suppliers import SupplierRecord, SupplierRepo
from app.flows.definition import FlowDefinition


class SupplierNotFound(Exception):
    """No Supplier has this id."""


class DuplicateSupplier(Exception):
    """Another Supplier already has this name."""


class FlowInvalid(Exception):
    """The flow definition failed validation. `messages` say why, for the editor."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


class ManualLoginUnavailable(Exception):
    """A manual browser cannot start for this Supplier yet."""


@dataclass(frozen=True)
class SupplierView:
    """A Supplier as the dashboard shows it, with derived health. No password."""

    id: int
    name: str
    site_url: str
    stock_source: str
    interval_min: int
    out_confirm_reads: int
    in_confirm_reads: int
    confirm_gap_min: int
    removed_as_unknown: bool
    max_quantity: int
    two_fa_methods: list[str]
    code_window_min: int
    paused: bool
    pause_reason: str | None
    health: str
    last_success_at: datetime | None
    session_age_s: int | None
    listing_count: int


@dataclass(frozen=True)
class ManualLoginView:
    id: int
    state: str
    expires_at: datetime
    browser_url: str
    error: str | None


def is_overdue(supplier: SupplierRecord, now: datetime) -> bool:
    """Whether the last successful check is older than twice the interval.

    A Supplier never checked has no last success, so it is not overdue (it is Stale).
    """
    if supplier.last_success_at is None:
        return False
    return (now - supplier.last_success_at).total_seconds() > 2 * supplier.interval_min * 60


def supplier_health(supplier: SupplierRecord, now: datetime) -> str:
    """Return paused, needs_code, blocked, stale or healthy, most urgent first."""
    if supplier.paused:
        return "paused"
    if supplier.waiting_for_code_until is not None and supplier.waiting_for_code_until > now:
        return "needs_code"
    if supplier.blocked:
        return "blocked"
    if supplier.last_success_at is None or is_overdue(supplier, now):
        return "stale"
    return "healthy"


def _view(session: Session, supplier: SupplierRecord, now: datetime) -> SupplierView:
    listings = CatalogRepo(session).list_listings(supplier_id=supplier.id, limit=1).total
    saved = supplier.session_saved_at
    return SupplierView(
        supplier.id, supplier.name, supplier.site_url, supplier.stock_source,
        supplier.interval_min, supplier.out_confirm_reads, supplier.in_confirm_reads,
        supplier.confirm_gap_min, supplier.removed_as_unknown, supplier.max_quantity,
        supplier.two_fa_methods, supplier.code_window_min, supplier.paused,
        supplier.pause_reason, supplier_health(supplier, now), supplier.last_success_at,
        None if saved is None else int((now - saved).total_seconds()), listings,
    )


def _record(session: Session, box: SecretBox, supplier_id: int) -> SupplierRecord:
    record = SupplierRepo(session, box).get(supplier_id)
    if record is None:
        raise SupplierNotFound(supplier_id)
    return record


def list_suppliers(session: Session, box: SecretBox, now: datetime) -> list[SupplierView]:
    """Return every Supplier by name."""
    return [_view(session, s, now) for s in SupplierRepo(session, box).list()]


def get_supplier(session: Session, box: SecretBox, now: datetime, supplier_id: int) -> SupplierView:
    """Return one Supplier.

    Raises:
        SupplierNotFound: for an unknown id.
    """
    return _view(session, _record(session, box, supplier_id), now)


def create_supplier(
    session: Session, box: SecretBox, now: datetime, name: str, site_url: str, **fields: Any
) -> SupplierView:
    """Add a Supplier; unset fields take the PLAN.md defaults.

    Raises:
        DuplicateSupplier: if the name is taken.
    """
    try:
        record = SupplierRepo(session, box).create(name=name, site_url=site_url, now=now, **fields)
    except IntegrityError:
        session.rollback()
        raise DuplicateSupplier(name) from None
    return _view(session, record, now)


def update_supplier(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, **fields: Any
) -> SupplierView:
    """Change only the given fields.

    Raises:
        SupplierNotFound: for an unknown id.
        DuplicateSupplier: if renaming onto an existing name.
    """
    _record(session, box, supplier_id)
    try:
        record = SupplierRepo(session, box).update(supplier_id, **fields)
    except IntegrityError:
        session.rollback()
        raise DuplicateSupplier(str(fields.get("name"))) from None
    return _view(session, record, now)


def delete_supplier(session: Session, box: SecretBox, supplier_id: int) -> None:
    """Remove a Supplier and everything under it.

    Raises:
        SupplierNotFound: for an unknown id.
    """
    _record(session, box, supplier_id)
    SupplierRepo(session, box).delete(supplier_id)


def set_credentials(
    session: Session, box: SecretBox, supplier_id: int, username: str, password: str
) -> None:
    """Store the Supplier login, encrypted. Raises SupplierNotFound."""
    _record(session, box, supplier_id)
    SupplierRepo(session, box).set_credentials(supplier_id, username, password)


def credentials_status(
    session: Session, box: SecretBox, supplier_id: int
) -> tuple[str | None, bool]:
    """Return the username and whether a password is set (never the password)."""
    record = _record(session, box, supplier_id)
    return record.username, record.has_password


def get_flow(session: Session, box: SecretBox, supplier_id: int) -> dict[str, Any] | None:
    """Return the editor draft first, otherwise the active flow."""
    _record(session, box, supplier_id)
    repo = SupplierRepo(session, box)
    return repo.get_flow_draft(supplier_id) or repo.get_flow(supplier_id)


def save_flow(
    session: Session, box: SecretBox, supplier_id: int, data: dict[str, Any]
) -> dict[str, Any]:
    """Store an incomplete editor draft, or promote a runnable definition.

    Raises:
        SupplierNotFound: for an unknown id.
        FlowInvalid: when even the draft is malformed; nothing is saved.
    """
    _record(session, box, supplier_id)
    try:
        flow = FlowDefinition.model_validate(data, context={"draft": True})
    except ValidationError as exc:
        raise FlowInvalid(
            [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}".lstrip(": ") for e in exc.errors()]
        ) from exc
    stored = flow.model_dump(mode="json")
    repo = SupplierRepo(session, box)
    try:
        FlowDefinition.model_validate(stored)
    except ValidationError:
        repo.set_flow_draft(supplier_id, stored)
    else:
        repo.set_flow(supplier_id, stored)
    return stored


def queue_action(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, kind: str
) -> None:
    """Queue a `login` or `check_supplier` job for the worker, unless one is already open.

    A double click must not make the worker hit the Supplier's site twice, and a second
    run would count as another confirmation read. Raises SupplierNotFound.
    """
    _record(session, box, supplier_id)
    _enqueue_once(session, now, supplier_id, kind)


def _manual_view(job: Any, browser_url: str) -> ManualLoginView:
    expires_at = datetime.fromisoformat(str(job.payload["expires_at"]))
    state = str(job.payload.get("manual_state", "queued"))
    if job.state == "failed" and state in {"queued", "ready"}:
        state = "failed"
    return ManualLoginView(
        job.id, state, expires_at,
        browser_url, job.payload.get("error") or job.last_error,
    )


def start_manual_login(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, browser_url: str
) -> ManualLoginView:
    """Queue one short-lived visible-browser login, idempotently."""
    _record(session, box, supplier_id)
    if SupplierRepo(session, box).get_flow(supplier_id) is None:
        raise ManualLoginUnavailable("Save a complete flow before starting manual login")
    jobs = JobRepo(session)
    latest = jobs.latest("manual_login", supplier_id)
    if latest is not None:
        expires_at = datetime.fromisoformat(str(latest.payload["expires_at"]))
        if latest.state in {"queued", "running"} and expires_at <= now:
            jobs.set_result(latest.id, "expired")
            latest = jobs.latest("manual_login", supplier_id)
    if latest is not None and latest.state in {"queued", "running"}:
        return _manual_view(latest, browser_url)
    expires_at = now + timedelta(minutes=10)
    job_id = jobs.enqueue(
        "manual_login", supplier_id,
        {"manual_state": "queued", "expires_at": expires_at.isoformat()}, now, now,
    )
    latest = jobs.latest("manual_login", supplier_id)
    assert latest is not None and latest.id == job_id
    return _manual_view(latest, browser_url)


def get_manual_login(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, browser_url: str
) -> ManualLoginView | None:
    """Return the newest manual-login attempt for a Supplier."""
    _record(session, box, supplier_id)
    jobs = JobRepo(session)
    job = jobs.latest("manual_login", supplier_id)
    if job is not None:
        expires_at = datetime.fromisoformat(str(job.payload["expires_at"]))
        if job.state in {"queued", "running"} and expires_at <= now:
            jobs.set_result(job.id, "expired")
            job = jobs.latest("manual_login", supplier_id)
    return None if job is None else _manual_view(job, browser_url)


def cancel_manual_login(session: Session, box: SecretBox, supplier_id: int) -> None:
    """Cancel a queued or visible manual browser session."""
    _record(session, box, supplier_id)
    jobs = JobRepo(session)
    job = jobs.latest("manual_login", supplier_id)
    if job is not None and job.state in {"queued", "running"}:
        jobs.set_result(job.id, "cancelled")


def retry_supplier(session: Session, box: SecretBox, now: datetime, supplier_id: int) -> None:
    """Clear a pause (and its failed attempts) and queue a check. Raises SupplierNotFound."""
    _record(session, box, supplier_id)
    SupplierRepo(session, box).update(
        supplier_id, paused=False, pause_reason=None, failed_login_attempts=0
    )
    _enqueue_once(session, now, supplier_id, "check_supplier")


def _enqueue_once(session: Session, now: datetime, supplier_id: int, kind: str) -> None:
    jobs = JobRepo(session)
    if not jobs.has_open_job(kind, supplier_id):
        jobs.enqueue(kind, supplier_id, {}, run_after=now, now=now)


def list_runs(session: Session, box: SecretBox, supplier_id: int) -> list[RunRecord]:
    """Return a Supplier's runs, newest first. Raises SupplierNotFound."""
    _record(session, box, supplier_id)
    return RunRepo(session).list_for_supplier(supplier_id)
