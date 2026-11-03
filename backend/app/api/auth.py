"""Sign-in routes. Parse the request, call the auth service, set or clear the cookie."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.deps import SESSION_COOKIE, Box, Db, Now, current_user
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth")


class SignInBody(BaseModel):
    """What the sign-in form sends."""

    username: str
    password: str
    totp: str


class Me(BaseModel):
    """The signed-in admin."""

    username: str


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(body: SignInBody, request: Request, session: Db, box: Box, now: Now) -> Response:
    """Sign in with password and TOTP code.

    Returns 204 and sets an httponly, SameSite=Strict session cookie. Raises 401 with a
    message that never says which part was wrong, and 429 after 5 failures for the
    username in 15 minutes.
    """
    try:
        token = auth_service.sign_in(session, box, now, body.username, body.password, body.totp)
    except auth_service.TooManyAttempts:
        raise HTTPException(status_code=429, detail="Too many attempts, try again later") from None
    except auth_service.SignInFailed:
        raise HTTPException(status_code=401, detail="Sign in failed") from None
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="strict",
        secure=request.app.state.secure_cookies,
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
    )
    return response


@router.get("/me")
def me(username: str = Depends(current_user)) -> Me:
    """Return who is signed in (401 if nobody is)."""
    return Me(username=username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, session: Db, box: Box, _: str = Depends(current_user)) -> Response:
    """End the session and clear the cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_service.sign_out(session, box, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE)
    return response
