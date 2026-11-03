"""A Playwright browser context for one Supplier visit.

Not responsible for what happens on the pages.
"""

import json
from collections.abc import Sequence
from types import TracebackType
from typing import Any, cast

from playwright.sync_api import Browser, BrowserContext, Error
from playwright.sync_api import Page as PlaywrightPage

from app.flows.page import PageError, PageResponse


class SessionNotOpenError(Exception):
    """The session was used before entering it with `with`."""


class PlaywrightPageAdapter:
    """Turns Playwright errors (timeouts, navigation failures) into `PageError`."""

    def __init__(self, page: PlaywrightPage) -> None:
        self._page = page

    @property
    def url(self) -> str:
        """The current URL."""
        return self._page.url

    def goto(self, url: str) -> PageResponse | None:
        """Navigate and return the final response.

        Raises:
            PageError: on a timeout or navigation failure.
        """
        try:
            return self._page.goto(url)
        except Error as exc:
            raise PageError(f"could not open {url}") from exc

    def fill(self, selector: str, value: str) -> None:
        """Type `value` into the field. Raises PageError if it cannot be found."""
        try:
            self._page.fill(selector, value)
        except Error as exc:
            raise PageError(f"could not fill {selector}") from exc

    def click(self, selector: str) -> None:
        """Click the element. Raises PageError if it cannot be clicked."""
        try:
            self._page.click(selector)
        except Error as exc:
            raise PageError(f"could not click {selector}") from exc

    def is_visible(self, selector: str) -> bool:
        """Whether the element is visible right now."""
        try:
            return self._page.is_visible(selector)
        except Error as exc:
            raise PageError(f"could not check {selector}") from exc

    def inner_text(self, selector: str) -> str:
        """Visible text of the element. Raises PageError if it cannot be read."""
        try:
            return self._page.inner_text(selector)
        except Error as exc:
            raise PageError(f"could not read {selector}") from exc

    def screenshot(self, mask_selectors: Sequence[str]) -> bytes:
        """A PNG with the masked elements covered. Raises PageError if it cannot be taken."""
        try:
            return self._page.screenshot(mask=[self._page.locator(s) for s in mask_selectors])
        except Error as exc:
            raise PageError("could not take a screenshot") from exc

    def content(self) -> str:
        """The page HTML. Raises PageError if the page is gone."""
        try:
            return self._page.content()
        except Error as exc:
            raise PageError("could not read the page") from exc


class PlaywrightSupplierSession:
    """Opens an isolated context and page, closed on exit."""

    def __init__(self, browser: Browser) -> None:
        self._browser = browser
        self._context: BrowserContext | None = None
        self._page: PlaywrightPageAdapter | None = None

    def __enter__(self) -> "PlaywrightSupplierSession":
        self._replace_context()
        return self

    def _replace_context(self, storage_state: dict[str, Any] | None = None) -> None:
        if self._context is not None:
            self._context.close()
        self._context = self._browser.new_context(storage_state=cast(Any, storage_state))
        self._page = PlaywrightPageAdapter(self._context.new_page())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._context is not None:
            self._context.close()

    @property
    def page(self) -> PlaywrightPageAdapter:
        """The tab to drive. Raises SessionNotOpenError before `with`."""
        if self._page is None:
            raise SessionNotOpenError("open the session with `with` first")
        return self._page

    def _open_context(self) -> BrowserContext:
        if self._context is None:
            raise SessionNotOpenError("open the session with `with` first")
        return self._context

    def storage_state_json(self) -> str:
        """Return cookies and local storage as Playwright storage-state JSON."""
        return json.dumps(self._open_context().storage_state())

    def load_storage_state_json(self, state_json: str) -> None:
        """Restore storage state, accepting legacy cookie-list JSON."""
        state: Any = json.loads(state_json)
        try:
            if isinstance(state, list):
                self._open_context().add_cookies(state)
            elif isinstance(state, dict):
                self._replace_context(state)
            else:
                raise ValueError("browser state must be an object or cookie list")
        except Error as exc:
            raise PageError("could not restore saved cookies") from exc

    def clear_storage_state(self) -> None:
        """Replace the current context with an empty one."""
        try:
            self._replace_context()
        except Error as exc:
            raise PageError("could not clear browser state") from exc
