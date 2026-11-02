"""The slice of a browser page the flows use, so they do not depend on Playwright.

Playwright's `Page` satisfies these structurally.
"""

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
