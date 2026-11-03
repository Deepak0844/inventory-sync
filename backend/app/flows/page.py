"""The slice of a browser page the flows use, so they do not depend on Playwright.

Playwright's `Page` satisfies these structurally.
"""

from collections.abc import Sequence
from typing import Protocol


class PageError(Exception):
    """The browser failed to do something (timeout, navigation error, closed page)."""


class PageResponse(Protocol):
    """The response to a navigation."""

    @property
    def status(self) -> int:
        """HTTP status code."""
        ...


class Page(Protocol):
    """A browser tab."""

    @property
    def url(self) -> str:
        """The current URL."""
        ...

    def goto(self, url: str) -> PageResponse | None:
        """Navigate and return the final response."""
        ...

    def fill(self, selector: str, value: str) -> None:
        """Type `value` into the field."""
        ...

    def click(self, selector: str) -> None:
        """Click the element and wait for any navigation it starts."""
        ...

    def is_visible(self, selector: str) -> bool:
        """Whether the element is visible right now."""
        ...

    def inner_text(self, selector: str) -> str:
        """Visible text of the element."""
        ...

    def content(self) -> str:
        """The page HTML."""
        ...

    def screenshot(self, mask_selectors: Sequence[str]) -> bytes:
        """A PNG of the page with every element matching `mask_selectors` painted over."""
        ...


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

    def clear_cookies(self) -> None:
        """Forget all cookies, so a failed saved session does not leak into a fresh login."""
        ...
