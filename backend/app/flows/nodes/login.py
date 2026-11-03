"""Node types for 2FA and sessions: await_code and save_session."""

from typing import Literal

from pydantic import BaseModel, Field

from app.flows.login_codes import CodeSource, MailboxCodeSource, await_login_code
from app.flows.nodes.base import BaseNode, FlowContext, FlowFailure
from app.flows.results import LoginResult


class EmailRule(BaseModel):
    """Where the Supplier's code email comes from and how to find the code in it."""

    sender: str = Field(min_length=1)
    pattern: str = Field(min_length=1)


class AwaitCode(BaseNode):
    """Wait for a Login Code from the dashboard and/or the mailbox, first one wins."""

    type: Literal["await_code"] = "await_code"
    methods: list[Literal["ui_code", "email_code"]] = Field(min_length=1)
    email: EmailRule | None = None
    timeout_s: float = 600.0

    def run(self, ctx: FlowContext) -> str | None:
        """Store the code in the context.

        Raises:
            FlowFailure: CODE_TIMEOUT if nothing arrives in time. That is not a
                failed attempt.
        """
        sources: list[CodeSource] = []
        if "ui_code" in self.methods:
            sources.append(ctx.pasted_codes)
        if "email_code" in self.methods and self.email and ctx.fetch_mail:
            sources.append(MailboxCodeSource(ctx.fetch_mail, self.email.sender, self.email.pattern))
        if not sources:
            # Waiting would only burn the whole timeout with no way for a code to arrive.
            raise FlowFailure(LoginResult.FLOW_FAILURE, "no usable Login Code source")
        requested_at = ctx.clock.now() if ctx.last_click_at is None else ctx.last_click_at
        code = await_login_code(sources, ctx.clock, requested_at, self.timeout_s, ctx.poll)
        if code is None:
            raise FlowFailure(LoginResult.CODE_TIMEOUT)
        ctx.code = code
        return None


class SaveSession(BaseNode):
    """Save the browser's session state, encrypted, for the next run."""

    type: Literal["save_session"] = "save_session"

    def run(self, ctx: FlowContext) -> str | None:
        """Encrypt and store the current browser state."""
        ctx.store.save(ctx.session.storage_state_json())
        return None
