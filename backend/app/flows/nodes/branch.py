"""The branch node: follow the "yes" or "no" edge depending on the page."""

from typing import Literal

from app.flows.nodes.base import BaseNode, FlowContext


class Branch(BaseNode):
    """Choose a path by whether an element is visible (for example a cookie banner)."""

    type: Literal["branch"] = "branch"
    if_visible: str

    def run(self, ctx: FlowContext) -> str | None:
        """Return "yes" when the element is visible, otherwise "no"."""
        return "yes" if ctx.session.page.is_visible(self.if_visible) else "no"
