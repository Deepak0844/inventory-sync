"""Route for pasting a Login Code from the dashboard.

Not responsible for waiting for or using the code; the login flow does that.
"""

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, field_validator

router = APIRouter()


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


@router.post("/login-code", status_code=status.HTTP_202_ACCEPTED)
def submit_login_code(body: LoginCodeBody, request: Request) -> None:
    """Hand a pasted Login Code to the run that is waiting for one.

    Returns 202: the code is accepted for use, not yet known to be correct.
    Responds 422 if the code is blank.
    """
    request.app.state.pasted_codes.submit(body.code)
