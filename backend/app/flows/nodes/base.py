"""The Node interface and the state nodes share while a flow runs.

Not responsible for walking the flow; `app.flows.runner` does that, and knows
nothing about individual node types.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.core.clock import Clock
from app.flows.login_codes import CodeSource
from app.flows.page import BrowserSession
from app.flows.results import Credentials, LoginResult
from app.flows.session_store import EncryptedSessionStore
from app.mail.codes import MailMessage

ALLOWED_VARIABLES = frozenset({"credentials.username", "credentials.password", "code"})
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class FlowFailure(Exception):
    """A node could not do its job. Carries how the login run should be reported."""

    def __init__(self, result: LoginResult, detail: str = "") -> None:
        super().__init__(detail or result.value)
        self.result = result


@dataclass
class FlowContext:
    """What a node can see and change during one run."""

    session: BrowserSession
    store: EncryptedSessionStore
    credentials: Credentials
    pasted_codes: CodeSource
    fetch_mail: Callable[[], Sequence[MailMessage]] | None
    clock: Clock
    poll: float
    code: str | None = None
    last_click_at: float = 0.0

    def render(self, template: str) -> str:
        """Fill `{{credentials.username}}`, `{{credentials.password}}` and `{{code}}`.

        Raises:
            FlowFailure: if `{{code}}` is used before a code has arrived.
        """

        def value(match: re.Match[str]) -> str:
            name = match.group(1)
            if name == "credentials.username":
                return self.credentials.username
            if name == "credentials.password":
                return self.credentials.password
            if self.code is None:
                raise FlowFailure(LoginResult.FLOW_FAILURE, "{{code}} used before a code arrived")
            return self.code

        return _PLACEHOLDER.sub(value, template)


def unknown_variables(template: str) -> list[str]:
    """Return placeholders in `template` that flows are not allowed to use."""
    return [n for n in _PLACEHOLDER.findall(template) if n not in ALLOWED_VARIABLES]


class BaseNode(BaseModel):
    """Base class for flow nodes: a Pydantic model with a `run` method.

    To add a node type, subclass this with a `type: Literal[...]` field and add
    the class to `FlowNode` in `app.flows.nodes`. The runner does not change.
    """

    model_config = ConfigDict(extra="forbid")

    id: str

    def run(self, ctx: FlowContext) -> str | None:
        """Do the step. Return a branch label to follow, or None for the plain edge.

        Raises:
            FlowFailure: to stop the run with a specific result.
            PageError: on a browser problem (the runner reports BROWSER_ERROR).
        """
        raise NotImplementedError
