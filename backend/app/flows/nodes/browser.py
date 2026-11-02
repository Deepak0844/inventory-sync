"""Node types that drive the page: goto, fill, click and wait_for."""

from typing import Literal

from pydantic import field_validator

from app.flows.nodes.base import BaseNode, FlowContext, FlowFailure, unknown_variables
from app.flows.results import LoginResult


class Goto(BaseNode):
    """Open a URL."""

    type: Literal["goto"] = "goto"
    url: str

    def run(self, ctx: FlowContext) -> str | None:
        """Navigate the page to `url`."""
        ctx.session.page.goto(self.url)
        return None


class Fill(BaseNode):
    """Type into a field. `mask` keeps the value out of screenshots and logs."""

    type: Literal["fill"] = "fill"
    selector: str
    value: str
    mask: bool = False

    @field_validator("value")
    @classmethod
    def _only_known_variables(cls, value: str) -> str:
        """Reject a typo like `{{credentials.usernam}}` when the flow is loaded."""
        bad = unknown_variables(value)
        if bad:
            raise ValueError(f"unknown template variable {bad[0]}")
        return value

    def run(self, ctx: FlowContext) -> str | None:
        """Fill the field with the rendered value."""
        ctx.session.page.fill(self.selector, ctx.render(self.value))
        return None


class Click(BaseNode):
    """Click an element."""

    type: Literal["click"] = "click"
    selector: str

    def run(self, ctx: FlowContext) -> str | None:
        """Click, noting the time first so a code email sent right after still counts as new."""
        ctx.last_click_at = ctx.clock.now()
        ctx.session.page.click(self.selector)
        return None


class WaitFor(BaseNode):
    """Wait until an element is visible.

    The `role` says what a timeout means: a `code_prompt` that never appears
    means bad credentials, and a `logged_in_marker` that never appears means a
    wrong code (or bad credentials when no code was entered).
    """

    type: Literal["wait_for"] = "wait_for"
    selector: str
    role: Literal["logged_in_marker", "code_prompt"] | None = None
    timeout_s: float = 5.0

    def run(self, ctx: FlowContext) -> str | None:
        """Poll until visible.

        Raises:
            FlowFailure: if the element does not appear within `timeout_s`.
        """
        page = ctx.session.page
        deadline = ctx.clock.now() + self.timeout_s
        while not page.is_visible(self.selector):
            if ctx.clock.now() >= deadline:
                raise FlowFailure(self._failure(ctx), f"{self.selector} never appeared")
            ctx.clock.sleep(0.2)
        return None

    def _failure(self, ctx: FlowContext) -> LoginResult:
        if self.role == "code_prompt":
            return LoginResult.BAD_CREDENTIALS
        if self.role == "logged_in_marker":
            return LoginResult.BAD_CREDENTIALS if ctx.code is None else LoginResult.WRONG_CODE
        return LoginResult.FLOW_FAILURE
