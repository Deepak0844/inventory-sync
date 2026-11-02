"""Local mock Supplier: login, emailed 2FA code and stock pages, with failure switches.

For tests only. Not responsible for modelling any real Supplier's markup.
"""

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

SENDER = "no-reply@mock-supplier.test"
USERNAME = "shop"
PASSWORD = "pw"


def _random_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@dataclass
class Email:
    """A code email, visible in the outbox once `available_at` has passed."""

    sender: str
    body: str
    sent_at: float
    available_at: float


@dataclass
class MockState:
    """Everything the mock Supplier remembers, with the clock and codes injectable."""

    code_generator: Callable[[], str] = _random_code
    clock: Callable[[], float] = time.time
    code: str | None = None
    sessions: set[str] = field(default_factory=set)
    out_of_stock: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)
    changed_selector: bool = False
    captcha: bool = False
    email_delay: float = 0.0
    outbox: list[Email] = field(default_factory=list)


class StockBody(BaseModel):
    """Body for flipping a product's stock."""

    in_stock: bool


class SelectorBody(BaseModel):
    """Body for the changed-selector switch."""

    changed: bool


class CaptchaBody(BaseModel):
    """Body for the CAPTCHA switch."""

    on: bool


class DelayBody(BaseModel):
    """Body for the email delay switch."""

    seconds: float


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html><body>{body}</body></html>", status_code=status)


def create_mock_app(state: MockState | None = None) -> FastAPI:
    """Build the mock Supplier. Pass `state` to control codes and time in tests."""
    state = state or MockState()
    app = FastAPI(title="Mock Supplier")

    def logged_in(request: Request) -> bool:
        return request.cookies.get("session") in state.sessions

    @app.get("/login")
    def login_page() -> HTMLResponse:
        return _page(
            '<form method="post" action="/login">'
            '<input name="username"><input name="password" type="password">'
            '<button type="submit">Sign in</button></form>'
        )

    @app.post("/login", response_model=None)
    def login(username: str = Form(), password: str = Form()) -> Response:
        if state.captcha:
            return _page("<p>Please complete the CAPTCHA</p>", 403)
        if (username, password) != (USERNAME, PASSWORD):
            return _page("<p>Wrong username or password</p>", 401)
        response = RedirectResponse("/verify", status_code=303)
        response.set_cookie("pre_auth", "1")
        return response

    @app.get("/verify", response_model=None)
    def verify_page(request: Request) -> Response:
        if request.cookies.get("pre_auth") != "1":
            return RedirectResponse("/login", status_code=303)
        now = state.clock()
        state.code = state.code_generator()
        state.outbox.append(
            Email(SENDER, f"Your code is {state.code}", now, now + state.email_delay)
        )
        return _page(
            '<p>Enter the code</p><form method="post" action="/verify">'
            '<input name="code"><button type="submit">Verify</button></form>'
        )

    @app.post("/verify", response_model=None)
    def verify(request: Request, code: str = Form()) -> Response:
        if state.captcha:
            return _page("<p>Please complete the CAPTCHA</p>", 403)
        if request.cookies.get("pre_auth") != "1" or code != state.code:
            return _page("<p>Wrong code</p>", 401)
        token = secrets.token_hex(8)
        state.sessions.add(token)
        response = RedirectResponse("/account", status_code=303)
        response.set_cookie("session", token)
        return response

    @app.get("/account", response_model=None)
    def account(request: Request) -> Response:
        if not logged_in(request):
            return RedirectResponse("/login", status_code=303)
        return _page('<nav data-testid="account-menu">My account</nav>')

    @app.get("/product/{product_id}", response_model=None)
    def product(request: Request, product_id: str) -> Response:
        if not logged_in(request):
            return RedirectResponse("/login", status_code=303)
        if product_id in state.removed:
            return _page("<p>Not found</p>", 404)
        label = "Out of stock" if product_id in state.out_of_stock else "In stock"
        element_id = "availability" if state.changed_selector else "stock"
        return _page(f'<h1>Product {product_id}</h1><p id="{element_id}">{label}</p>')

    @app.post("/_control/stock/{product_id}")
    def set_stock(product_id: str, body: StockBody) -> None:
        (state.out_of_stock.discard if body.in_stock else state.out_of_stock.add)(product_id)

    @app.post("/_control/remove/{product_id}")
    def remove(product_id: str) -> None:
        state.removed.add(product_id)

    @app.post("/_control/selector")
    def set_selector(body: SelectorBody) -> None:
        state.changed_selector = body.changed

    @app.post("/_control/captcha")
    def set_captcha(body: CaptchaBody) -> None:
        state.captcha = body.on

    @app.post("/_control/email_delay")
    def set_email_delay(body: DelayBody) -> None:
        state.email_delay = body.seconds

    @app.get("/_control/outbox")
    def outbox() -> list[dict[str, object]]:
        now = state.clock()
        return [
            {"sender": m.sender, "body": m.body, "sent_at": m.sent_at}
            for m in state.outbox
            if m.available_at <= now
        ]

    return app
