"""Login Code routes: which Suppliers are waiting, and pasting a code."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, field_validator

from app.api.deps import Box, Db, Now, protected
from app.services import login_codes as service

router = APIRouter(**protected(tags=["login code"]))


class PendingOut(BaseModel):
    supplier_id: int
    supplier_name: str
    expires_at: datetime


class LoginCodeBody(BaseModel):
    """A Login Code as typed by the store owner."""

    code: str

    @field_validator("code")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Trim the code and reject an empty one."""
        value = value.strip()
        if not value:
            raise ValueError("code must not be blank")
        return value


@router.get("/login-code/pending")
def pending(session: Db, box: Box, now: Now) -> list[PendingOut]:
    """List Suppliers whose login is waiting for a code. The dashboard polls this."""
    return [PendingOut(supplier_id=p.supplier_id, supplier_name=p.supplier_name,
                       expires_at=p.expires_at) for p in service.pending_codes(session, box, now)]


@router.post("/suppliers/{supplier_id}/login-code", status_code=status.HTTP_202_ACCEPTED)
def submit(supplier_id: int, body: LoginCodeBody, session: Db, box: Box, now: Now) -> Response:
    """Hand a pasted code to the waiting run.

    Returns 202: the code is accepted for use, not yet known to be correct. 404 when that
    Supplier is not waiting, 422 for a blank code.
    """
    try:
        service.submit_code(session, box, now, supplier_id, body.code)
    except service.NotWaitingForCode:
        raise HTTPException(status_code=404, detail="That Supplier is not waiting for a code") \
            from None
    return Response(status_code=status.HTTP_202_ACCEPTED)
