"""Pasting a Login Code for a Supplier whose run is waiting for one.

Not responsible for typing the code into the Supplier's site; the worker takes it
from the pasted_codes table. A code is only accepted while a prompt is open, so a
stale code can never be used by a later run.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.repos.codes import PastedCodeRepo
from app.db.repos.suppliers import SupplierRepo


class NotWaitingForCode(Exception):
    """The Supplier is unknown or has no open code prompt."""


@dataclass(frozen=True)
class PendingCode:
    """A Supplier whose login is waiting for a code until `expires_at`."""

    supplier_id: int
    supplier_name: str
    expires_at: datetime


def pending_codes(session: Session, box: SecretBox, now: datetime) -> list[PendingCode]:
    """Return the Suppliers with an open prompt, soonest deadline first."""
    waiting = [
        PendingCode(s.id, s.name, s.waiting_for_code_until)
        for s in SupplierRepo(session, box).list()
        if s.waiting_for_code_until is not None and s.waiting_for_code_until > now
    ]
    return sorted(waiting, key=lambda p: p.expires_at)


def submit_code(
    session: Session, box: SecretBox, now: datetime, supplier_id: int, code: str
) -> None:
    """Store a pasted code for the Supplier's waiting run.

    Raises:
        NotWaitingForCode: if the Supplier is unknown or no prompt is open.
    """
    supplier = SupplierRepo(session, box).get(supplier_id)
    until = None if supplier is None else supplier.waiting_for_code_until
    if until is None or until <= now:
        raise NotWaitingForCode(supplier_id)
    PastedCodeRepo(session, box).submit(supplier_id, code, now)
