"""The JSON flow definition the worker runs (PLAN.md section 11).

Not responsible for running a flow; `app.flows.runner` does. Everything wrong
with a definition is reported when it is loaded, not in the middle of a run.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.flows.nodes import FlowNode
from app.flows.nodes.branch import Branch
from app.flows.nodes.browser import Fill, WaitFor
from app.flows.nodes.login import AwaitCode, SaveSession

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
        if not self.nodes:
            raise ValueError("flow has no nodes")
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node id")
        if not any(isinstance(n, SaveSession) for n in self.nodes):
            raise ValueError("flow needs a save_session node, or every run asks for a new code")
        known = set(ids)
        for source, target, *_ in self.edges:
            if source not in known or target not in known:
                raise ValueError(f"edge {source}->{target} refers to an unknown node")
        branches = {n.id for n in self.nodes if isinstance(n, Branch)}
        for edge in self.edges:
            if len(edge) == 3 and edge[0] not in branches:
                raise ValueError(f"only branch nodes may have labeled edges ({edge[0]})")
        for node in self.nodes:
            labels = [e[2] if len(e) == 3 else None for e in self.edges if e[0] == node.id]
            if isinstance(node, Branch):
                if sorted(str(label) for label in labels) != ["no", "yes"]:
                    raise ValueError(f"branch {node.id} needs exactly a yes and a no edge")
            elif len(labels) > 1:
                raise ValueError(f"node {node.id} has more than one outgoing edge")
        order = self._topological_order()
        self._check_nodes()
        self._check_marker_on_every_path(order)
        return self

    def _topological_order(self) -> list[str]:
        """Kahn's algorithm. Also proves there is one start and every node is reachable."""
        indegree = {n.id: 0 for n in self.nodes}
        for edge in self.edges:
            indegree[edge[1]] += 1
        if sum(1 for d in indegree.values() if d == 0) != 1:
            raise ValueError("flow must have exactly one start node (found a cycle or a gap)")
        queue = [i for i, d in indegree.items() if d == 0]
        order: list[str] = []
        while queue:
            current = queue.pop()
            order.append(current)
            for edge in self.edges:
                if edge[0] == current:
                    indegree[edge[1]] -= 1
                    if indegree[edge[1]] == 0:
                        queue.append(edge[1])
        if len(order) != len(self.nodes):
            raise ValueError("flow contains a cycle")
        return order

    def _check_nodes(self) -> None:
        for node in self.nodes:
            if isinstance(node, AwaitCode) and "email_code" in node.methods and node.email is None:
                raise ValueError(f"await_code {node.id} lists email_code but has no email settings")
            if isinstance(node, Fill):
                continue
            for name, value in node:
                if isinstance(value, str) and "{{" in value:
                    raise ValueError(f"templates are only supported in fill ({node.id}.{name})")

    def _check_marker_on_every_path(self, order: list[str]) -> None:
        """Every path from the start to an end must pass the logged-in marker."""
        marker_ids = {
            n.id for n in self.nodes if isinstance(n, WaitFor) and n.role == "logged_in_marker"
        }
        if not marker_ids:
            raise ValueError("flow needs a wait_for node with role logged_in_marker")
        passes: dict[str, bool] = {}
        for node_id in reversed(order):
            children = [e[1] for e in self.edges if e[0] == node_id]
            passes[node_id] = node_id in marker_ids or (
                bool(children) and all(passes[c] for c in children)
            )
        if not passes[order[0]]:
            raise ValueError("the logged_in_marker wait_for must be reached on every path")

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
