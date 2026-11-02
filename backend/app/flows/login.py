"""Logging in to a Supplier: reuse a saved session, else password plus Login Code.

Not responsible for counting failed attempts across runs or pausing a Supplier;
callers act on the `LoginResult`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.core.clock import Clock
from app.flows.login_codes import CodeSource, await_login_code
from app.flows.page import Page
from app.flows.session_store import EncryptedSessionStore
from app.flows.supplier_flow import SupplierFlow


@dataclass(frozen=True)
class Credentials:
    """A Supplier account. The password is kept out of reprs and logs."""

    username: str
    password: str = field(repr=False)


class LoginResult(Enum):
    """How a login attempt ended. Only WRONG_CODE and BAD_CREDENTIALS are failed attempts."""

    SESSION_REUSED = "session_reused"
    LOGGED_IN = "logged_in"
    WRONG_CODE = "wrong_code"
    BAD_CREDENTIALS = "bad_credentials"
    CODE_TIMEOUT = "code_timeout"
    BLOCKED = "blocked"


class BrowserSession(Protocol):
    """A page plus the ability to save and restore its cookies."""

    @property
    def page(self) -> Page:
        """The tab to drive."""
        ...

    def cookies_json(self) -> str:
        """Cookies as JSON."""
        ...

    def load_cookies_json(self, cookies_json: str) -> None:
        """Restore saved cookies."""
        ...


def ensure_logged_in(
    session: BrowserSession,
    store: EncryptedSessionStore,
    flow: SupplierFlow,
    credentials: Credentials,
    code_sources: Sequence[CodeSource],
    clock: Clock,
    code_timeout: float,
    poll: float,
) -> LoginResult:
    """Make the session logged in, logging in only if the saved session is gone.

    Returns SESSION_REUSED when the saved cookies still show the logged-in
    marker, otherwise runs the full login and saves the new cookies on success.
    """
    page = session.page
    saved = store.load()
    if saved is not None:
        session.load_cookies_json(saved)
        page.goto(flow.base_url + flow.account_path)
        if page.is_visible(flow.logged_in_marker):
            return LoginResult.SESSION_REUSED
        store.clear()

    page.goto(flow.base_url + flow.login_path)
    page.fill(flow.username_selector, credentials.username)
    page.fill(flow.password_selector, credentials.password)
    # Taken before submitting so an email sent right after the click still counts as new.
    requested_at = clock.now()
    page.click(flow.submit_selector)

    if flow.blocked_text in page.content():
        return LoginResult.BLOCKED
    if flow.code_prompt_text not in page.content():
        return LoginResult.BAD_CREDENTIALS

    code = await_login_code(code_sources, clock, requested_at, code_timeout, poll)
    if code is None:
        return LoginResult.CODE_TIMEOUT
    page.fill(flow.code_selector, code)
    page.click(flow.submit_selector)
    if not page.is_visible(flow.logged_in_marker):
        return LoginResult.WRONG_CODE
    store.save(session.cookies_json())
    return LoginResult.LOGGED_IN
