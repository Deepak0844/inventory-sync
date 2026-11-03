"""Login Codes pasted in the dashboard, shared between the API and the worker.

Not responsible for judging a code; the worker types it into the Supplier's site.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.db.models import PastedCode


@dataclass(frozen=True)
class PastedCodeRecord:
    code: str
    submitted_at: datetime


class PastedCodeRepo:
    """Encrypted, single-use pasted codes."""

    def __init__(self, session: Session, box: SecretBox) -> None:
        self._s = session
        self._box = box

    def submit(self, supplier_id: int, code: str, now: datetime) -> None:
        """Store a pasted code for the Supplier's waiting run."""
        self._s.add(PastedCode(supplier_id=supplier_id, code_enc=self._box.encrypt(code),
                               submitted_at=now))
        self._s.commit()

    def take(self, supplier_id: int) -> PastedCodeRecord | None:
        """Return the latest pasted code and delete all of them, so none is reused."""
        rows = self._s.scalars(select(PastedCode).where(PastedCode.supplier_id == supplier_id)
                               .order_by(PastedCode.submitted_at.desc(), PastedCode.id.desc())
                               .with_for_update()).all()
        if not rows:
            return None
        latest = PastedCodeRecord(self._box.decrypt(rows[0].code_enc), rows[0].submitted_at)
        self._s.execute(delete(PastedCode).where(PastedCode.supplier_id == supplier_id))
        self._s.commit()
        return latest
