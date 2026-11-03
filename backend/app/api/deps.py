"""Request-scoped dependencies: the database session, the clock, and who is signed in.

Not responsible for any business rule; services own those.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.encryption import SecretBox
from app.services import auth as auth_service
from app.services.settings import ShopifyFactory

SESSION_COOKIE = "session"


def get_session(request: Request) -> Iterator[Session]:
    """Open one session for the request and close it afterwards."""
    with request.app.state.session_factory() as session:
        yield session


def get_box(request: Request) -> SecretBox:
    """The secret box built at startup."""
    box: SecretBox = request.app.state.box
    return box


def get_now(request: Request) -> datetime:
    """The current time, from the app's clock."""
    now: datetime = request.app.state.now()
    return now


def get_shopify_factory(request: Request) -> ShopifyFactory:
    """The factory for the Shopify connection check."""
    factory: ShopifyFactory = request.app.state.shopify_factory
    return factory


Db = Annotated[Session, Depends(get_session)]
Box = Annotated[SecretBox, Depends(get_box)]
Now = Annotated[datetime, Depends(get_now)]
Shopify = Annotated[ShopifyFactory, Depends(get_shopify_factory)]


def current_user(request: Request, session: Db, box: Box, now: Now) -> str:
    """Return the signed-in username or raise 401. Protects every /api route but sign-in."""
    token = request.cookies.get(SESSION_COOKIE)
    username = auth_service.username_for(session, box, token, now) if token else None
    if username is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return username


def protected(**kwargs: Any) -> dict[str, Any]:
    """Router arguments that put every route behind the sign-in check."""
    return {"prefix": "/api", "dependencies": [Depends(current_user)], **kwargs}
