"""A Playwright browser context for one Supplier visit.

Not responsible for what happens on the pages.
"""

import json
from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, BrowserContext
from playwright.sync_api import Page as PlaywrightPage


class PlaywrightSupplierSession:
    """Opens an isolated context and page, closed on exit."""

    def __init__(self, browser: Browser) -> None:
        self._browser = browser
        self._context: BrowserContext | None = None
        self.page: PlaywrightPage

    def __enter__(self) -> "PlaywrightSupplierSession":
        self._context = self._browser.new_context()
        self.page = self._context.new_page()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._context is not None:
            self._context.close()

    def cookies_json(self) -> str:
        """Return the context's cookies as JSON."""
        assert self._context is not None
        return json.dumps(self._context.cookies())

    def load_cookies_json(self, cookies_json: str) -> None:
        """Add previously saved cookies to the context."""
        assert self._context is not None
        cookies: list[Any] = json.loads(cookies_json)
        self._context.add_cookies(cookies)
