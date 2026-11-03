import { applyEdgeChanges, applyNodeChanges, type EdgeChange, type NodeChange } from "@xyflow/react";

import { flowMeta, flowToGraph, graphToFlow, makeEdge } from "./convert";
import type { EdgeLabel, ExtractRules, FlowDoc, FlowMeta, FlowNode, Graph, GraphNode, NodeType } from "./types";

/** The flow being edited: the settings around the graph, and the graph itself. */
export interface Draft {
  meta: FlowMeta;
  graph: Graph;
}

export type Change =
  | { kind: "add"; nodeType: NodeType; position: { x: number; y: number }; after?: string }
  | { kind: "update"; node: FlowNode }
  | { kind: "remove"; id: string }
  | { kind: "connect"; source: string; target: string; handle?: string | null }
  | { kind: "meta"; patch: Partial<FlowMeta> }
  | { kind: "extract"; patch: Partial<ExtractRules> }
  | { kind: "nodes"; changes: NodeChange<GraphNode>[] }
  | { kind: "edges"; changes: EdgeChange[] }
  | { kind: "replace"; flow: FlowDoc };

export function draftFromFlow(flow: FlowDoc): Draft {
  return { meta: flowMeta(flow), graph: flowToGraph(flow) };
}

export const draftToFlow = (draft: Draft): FlowDoc => graphToFlow(draft.graph, draft.meta);

/** A new step of the given type with fields ready to fill in. */
export function newNode(type: NodeType, id: string): FlowNode {
  switch (type) {
    case "goto": return { id, type, url: "" };
    case "fill": return { id, type, selector: "", value: "" };
    case "click": return { id, type, selector: "" };
    case "wait_for": return { id, type, selector: "", role: null, timeout_s: 5 };
    case "await_code": return { id, type, methods: ["ui_code"], email: null, timeout_s: 600 };
    case "branch": return { id, type, if_visible: "" };
    case "save_session": return { id, type };
  }
}

const nextId = (nodes: GraphNode[]) =>
  `n${Math.max(0, ...nodes.map((n) => Number(/(\d+)$/.exec(n.id)?.[1] ?? 0))) + 1}`;

function connect(draft: Draft, source: string, target: string, handle?: string | null): Draft {
  const from = draft.graph.nodes.find((n) => n.id === source)?.data.node;
  if (!from || source === target || !draft.graph.nodes.some((n) => n.id === target)) return draft;
  const isBranch = from.type === "branch";
  if (isBranch && handle !== "yes" && handle !== "no") return draft;
  const label = isBranch ? (handle as EdgeLabel) : undefined;
  const edge = makeEdge(source, target, label);
  if (draft.graph.edges.some((e) => e.id === edge.id)) return draft;
  // A step has one way forward; a Branch has one per path.
  const kept = draft.graph.edges.filter((e) => !(e.source === source && (!isBranch || e.sourceHandle === label)));
  return { ...draft, graph: { ...draft.graph, edges: [...kept, edge] } };
}

function remove(draft: Draft, id: string): Draft {
  return {
    ...draft,
    graph: {
      nodes: draft.graph.nodes.filter((n) => n.id !== id),
      edges: draft.graph.edges.filter((e) => e.source !== id && e.target !== id),
    },
  };
}

function add(draft: Draft, change: Extract<Change, { kind: "add" }>): Draft {
  const id = nextId(draft.graph.nodes);
  const node: GraphNode = {
    id,
    type: "flowNode",
    position: change.position,
    selected: true,
    data: { node: newNode(change.nodeType, id) },
  };
  const nodes = [...draft.graph.nodes.map((n) => ({ ...n, selected: false })), node];
  const next: Draft = { ...draft, graph: { ...draft.graph, nodes } };
  const from = change.after && draft.graph.nodes.find((n) => n.id === change.after)?.data.node;
  if (!from) return next;
  const outgoing = draft.graph.edges.filter((e) => e.source === from.id);
  const adding = node.data.node;

  if (from.type === "branch") {
    const used = new Set(outgoing.map((e) => e.sourceHandle));
    const free = (["yes", "no"] as const).find((l) => !used.has(l));
    if (free === undefined) return next;
    const placed = connect(next, from.id, id, free);
    // The other path already leads somewhere: a step on this path rejoins it, which is how an
    // optional step (such as closing a pop-up) is built.
    const other = outgoing.find((e) => e.sourceHandle);
    return other && adding.type !== "branch" ? relayout(connect(placed, id, other.target), id) : placed;
  }

  // Insert after the chosen step: it takes over the step's way forward, so a step added in the
  // middle of the flow is part of it instead of floating loose.
  const placed = connect(next, from.id, id);
  const onward = outgoing[0];
  if (!onward) return placed;
  return relayout(connect(placed, id, onward.target, adding.type === "branch" ? "no" : null), id);
}

/** Positions are not saved (the flow format has none), so a step inserted in the middle is
 * drawn by the same layout a loaded flow gets, instead of at the bottom with lines across. */
function relayout(draft: Draft, selectedId: string): Draft {
  const laid = draftFromFlow(draftToFlow(draft));
  const nodes = laid.graph.nodes.map((n) => ({ ...n, selected: n.id === selectedId }));
  return { ...draft, graph: { ...draft.graph, nodes, edges: laid.graph.edges } };
}

/** Applies one editing step. Returns the same draft when nothing changes. */
export function applyChange(draft: Draft, change: Change): Draft {
  switch (change.kind) {
    case "add":
      return add(draft, change);
    case "update":
      return {
        ...draft,
        graph: {
          ...draft.graph,
          nodes: draft.graph.nodes.map((n) => (n.id === change.node.id ? { ...n, data: { node: change.node } } : n)),
        },
      };
    case "remove":
      return remove(draft, change.id);
    case "connect":
      return connect(draft, change.source, change.target, change.handle);
    case "meta":
      return { ...draft, meta: { ...draft.meta, ...change.patch } };
    case "extract":
      return { ...draft, meta: { ...draft.meta, extract: { ...draft.meta.extract, ...change.patch } } };
    case "nodes": {
      const removed = change.changes.flatMap((c) => (c.type === "remove" ? [c.id] : []));
      const kept = change.changes.filter((c) => c.type !== "remove");
      const moved: Draft = { ...draft, graph: { ...draft.graph, nodes: applyNodeChanges(kept, draft.graph.nodes) } };
      return removed.reduce(remove, moved);
    }
    case "edges":
      return { ...draft, graph: { ...draft.graph, edges: applyEdgeChanges(change.changes, draft.graph.edges) } };
    case "replace":
      return draftFromFlow(change.flow);
  }
}
