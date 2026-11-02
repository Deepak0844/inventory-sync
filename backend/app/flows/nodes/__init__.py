"""All flow node types. Add a new node class to `FlowNode` to make it loadable."""

from typing import Annotated

from pydantic import Field

from app.flows.nodes.base import BaseNode, FlowContext, FlowFailure
from app.flows.nodes.branch import Branch
from app.flows.nodes.browser import Click, Fill, Goto, WaitFor
from app.flows.nodes.login import AwaitCode, SaveSession

FlowNode = Annotated[
    Goto | Fill | Click | WaitFor | AwaitCode | Branch | SaveSession,
    Field(discriminator="type"),
]

__all__ = ["BaseNode", "FlowContext", "FlowFailure", "FlowNode"]
