"""The JSON flow definition the worker runs (PLAN.md section 11).

Not responsible for running a flow; `app.flows.runner` does. Everything wrong
with a definition is reported when it is loaded, not in the middle of a run.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.flows.nodes import FlowNode
from app.flows.nodes.branch import Branch
from app.flows.nodes.browser import WaitFor

Edge = tuple[str, str] | tuple[str, str, str]


class Condition(BaseModel):
    """A text match, case-insensitive."""

    contains: str = Field(min_length=1)


class ExtractRules(BaseModel):
    """How to read a Listing's Stock Status."""

    stock_selector: str = Field(min_length=1)
    in_stock_if: Condition
    out_of_stock_if: Condition
    quantity_selector: str | None = None


class FlowDefinition(BaseModel):
    """One Supplier's login and extract flow."""

    model_config = ConfigDict(extra="forbid")

    supplier: str = Field(min_length=1)
    version: int
    login_path: str = Field(min_length=1)
    logged_in_url: str = Field(min_length=1)
    blocked_if: Condition
    nodes: list[FlowNode]
    edges: list[Edge]
    extract: ExtractRules

    @model_validator(mode="after")
    def _check_graph(self) -> "FlowDefinition":
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node id")
        known = set(ids)
        for source, target, *_ in self.edges:
            if source not in known or target not in known:
                raise ValueError(f"edge {source}->{target} refers to an unknown node")
        for node in self.nodes:
            labels = [e[2] if len(e) == 3 else None for e in self.edges if e[0] == node.id]
            if isinstance(node, Branch):
                if sorted(str(label) for label in labels) != ["no", "yes"]:
                    raise ValueError(f"branch {node.id} needs exactly a yes and a no edge")
            elif len(labels) > 1:
                raise ValueError(f"node {node.id} has more than one outgoing edge")
        if not self.nodes:
            raise ValueError("flow has no nodes")
        self._check_no_cycle()
        if not any(isinstance(n, WaitFor) and n.role == "logged_in_marker" for n in self.nodes):
            raise ValueError("flow needs a wait_for node with role logged_in_marker")
        return self

    def _check_no_cycle(self) -> None:
        targets = {e[1] for e in self.edges}
        starts = [n for n in self.nodes if n.id not in targets]
        if len(starts) != 1:
            raise ValueError("flow must have exactly one start node (found a cycle or a gap)")
        stack = [(starts[0].id, frozenset[str]())]
        while stack:
            node_id, path = stack.pop()
            if node_id in path:
                raise ValueError("flow contains a cycle")
            for edge in self.edges:
                if edge[0] == node_id:
                    stack.append((edge[1], path | {node_id}))

    @property
    def start(self) -> FlowNode:
        """The node with no incoming edge."""
        targets = {e[1] for e in self.edges}
        return next(n for n in self.nodes if n.id not in targets)

    @property
    def logged_in_marker(self) -> str:
        """Selector of the element only visible when signed in."""
        for node in self.nodes:
            if isinstance(node, WaitFor) and node.role == "logged_in_marker":
                return node.selector
        raise ValueError("unreachable: validated on load")  # pragma: no cover

    def next_node(self, node_id: str, label: str | None) -> FlowNode | None:
        """Follow the edge from `node_id` (matching `label` for a branch), or None at the end."""
        for edge in self.edges:
            if edge[0] == node_id and (edge[2] if len(edge) == 3 else None) == label:
                return next(n for n in self.nodes if n.id == edge[1])
        return None
