"""Suppliers, their encrypted credentials, flow and saved session.

Not responsible for deciding health or running anything. Records never carry a
password; `get_credentials` is the one explicit way to read it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.models import Supplier
from app.flows.results import Credentials

_EDITABLE = {
    "name", "site_url", "stock_source", "interval_min", "out_confirm_reads", "in_confirm_reads",
    "confirm_gap_min", "removed_as_unknown", "max_quantity", "two_fa_methods", "code_window_min",
    "paused", "pause_reason", "blocked", "failed_login_attempts", "last_success_at",
    "waiting_for_code_until",
}


@dataclass(frozen=True)
class SupplierRecord:
    """A Supplier as the API shows it (no password)."""

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
    username: str | None
    has_password: bool
    has_flow: bool
    paused: bool
    pause_reason: str | None
    blocked: bool
    failed_login_attempts: int
    last_success_at: datetime | None
    waiting_for_code_until: datetime | None
    session_saved_at: datetime | None


class SupplierRepo:
    """Supplier rows."""

    def __init__(self, session: Session, box: SecretBox) -> None:
        self._s = session
        self._box = box

    def create(self, name: str, site_url: str, now: datetime, **fields: Any) -> SupplierRecord:
        """Add a Supplier with the PLAN.md defaults, overridden by `fields`.

        Raises:
            ValueError: for a field that cannot be set.
        """
        _check(fields)
        supplier = Supplier(name=name, site_url=site_url, created_at=now,
                            two_fa_methods=["ui_code"], **fields)
        self._s.add(supplier)
        self._s.commit()
        return self._record(supplier)

    def get(self, supplier_id: int) -> SupplierRecord | None:
        """Return one Supplier, or None."""
        supplier = self._s.get(Supplier, supplier_id)
        return None if supplier is None else self._record(supplier)

    def list(self) -> list[SupplierRecord]:
        """Return every Supplier by name."""
        rows = self._s.scalars(select(Supplier).order_by(Supplier.name))
        return [self._record(s) for s in rows]

    def update(self, supplier_id: int, **fields: Any) -> SupplierRecord:
        """Change only the given fields.

        Raises:
            ValueError: for a field that cannot be set, or an unknown Supplier.
        """
        _check(fields)
        supplier = self._get(supplier_id)
        for key, value in fields.items():
            setattr(supplier, key, value)
        self._s.commit()
        return self._record(supplier)

    def delete(self, supplier_id: int) -> None:
        """Remove a Supplier and everything that belongs to it."""
        self._s.delete(self._get(supplier_id))
        self._s.commit()

    def set_credentials(self, supplier_id: int, username: str, password: str) -> None:
        """Store the login, encrypted."""
        supplier = self._get(supplier_id)
        supplier.username_enc = self._box.encrypt(username)
        supplier.password_enc = self._box.encrypt(password)
        self._s.commit()

    def get_credentials(self, supplier_id: int) -> Credentials | None:
        """Decrypt the login for the worker, or None if not set."""
        supplier = self._get(supplier_id)
        if supplier.username_enc is None or supplier.password_enc is None:
            return None
        return Credentials(self._box.decrypt(supplier.username_enc),
                           self._box.decrypt(supplier.password_enc))

    def set_flow(self, supplier_id: int, flow: dict[str, Any]) -> None:
        """Store the flow definition JSON (validated by the caller)."""
        self._get(supplier_id).flow_json = flow
        self._s.commit()

    def get_flow(self, supplier_id: int) -> dict[str, Any] | None:
        """Return the flow definition JSON, or None."""
        return self._get(supplier_id).flow_json

    def _get(self, supplier_id: int) -> Supplier:
        supplier = self._s.get(Supplier, supplier_id)
        if supplier is None:
            raise ValueError(f"no Supplier with id {supplier_id}")
        return supplier

    def _record(self, s: Supplier) -> SupplierRecord:
        return SupplierRecord(
            s.id, s.name, s.site_url, s.stock_source, s.interval_min, s.out_confirm_reads,
            s.in_confirm_reads, s.confirm_gap_min, s.removed_as_unknown, s.max_quantity,
            list(s.two_fa_methods),
            s.code_window_min,
            None if s.username_enc is None else self._box.decrypt(s.username_enc),
            s.password_enc is not None, s.flow_json is not None, s.paused, s.pause_reason,
            s.blocked, s.failed_login_attempts, s.last_success_at, s.waiting_for_code_until,
            s.session_saved_at,
        )


def _check(fields: dict[str, Any]) -> None:
    bad = set(fields) - _EDITABLE
    if bad:
        raise ValueError(f"cannot set {sorted(bad)}")


class SessionCookiesRepo:
    """A Supplier's saved cookies, as the `TextRepository` the session store expects.

    The caller wraps this in `EncryptedSessionStore`, which does the encrypting.
    """

    def __init__(self, session: Session, supplier_id: int, clock: Callable[[], datetime]) -> None:
        self._s = session
        self._id = supplier_id
        self._clock = clock

    def get(self) -> str | None:
        """Return the stored (already encrypted) text, or None."""
        supplier = self._s.get(Supplier, self._id)
        return None if supplier is None else supplier.session_cookies_enc

    def put(self, value: str | None) -> None:
        """Store the text, or clear it when None."""
        supplier = self._s.get(Supplier, self._id)
        if supplier is None:
            raise ValueError(f"no Supplier with id {self._id}")
        supplier.session_cookies_enc = value
        supplier.session_saved_at = None if value is None else self._clock()
        self._s.commit()
