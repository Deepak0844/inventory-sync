import type { EdgeLabel, FlowDoc, FlowEdge, FlowMeta, FlowNode, Graph, GraphEdge, GraphNode } from "./types";

const COLUMN = 280;
/** Vertical distance between steps on the canvas. */
export const ROW = 96;

type Point = { x: number; y: number };

const labelOf = (edge: FlowEdge): EdgeLabel | undefined => (edge.length === 3 ? edge[2] : undefined);

/** One React Flow edge. A Branch's yes/no paths use the matching handle and show their label. */
export function makeEdge(source: string, target: string, label?: EdgeLabel): GraphEdge {
  return {
    id: `${source}${label ? `:${label}` : ""}->${target}`,
    source,
    target,
    ...(label ? { sourceHandle: label, label } : {}),
  };
}

/**
 * Top-down layout. A Branch puts its yes path left and its no path right, a step where paths
 * meet sits under their middle, and a step that is not connected goes in its own column. Loops
 * cannot be laid out by depth, so their steps stack below the rest instead of hanging the page.
 */
function layout(nodes: FlowNode[], edges: FlowEdge[]): Map<string, Point> {
  const ids = new Set(nodes.map((n) => n.id));
  const incoming = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const children = new Map<string, FlowEdge[]>(nodes.map((n) => [n.id, []]));
  for (const edge of edges) {
    if (!ids.has(edge[0]) || !ids.has(edge[1])) continue;
    children.get(edge[0])?.push(edge);
    incoming.set(edge[1], (incoming.get(edge[1]) ?? 0) + 1);
  }

  const depth = new Map<string, number>();
  const candidates = new Map<string, number[]>();
  const positions = new Map<string, Point>();
  const queue = nodes.filter((n) => incoming.get(n.id) === 0).map((n) => n.id);
  queue.forEach((id, index) => {
    depth.set(id, 0);
    candidates.set(id, [index * COLUMN * 2]);
  });

  for (let at = 0; at < queue.length; at++) {
    const id = queue[at];
    const xs = candidates.get(id) ?? [0];
    const x = xs.reduce((a, b) => a + b, 0) / xs.length;
    positions.set(id, { x, y: (depth.get(id) ?? 0) * ROW });
    for (const edge of children.get(id) ?? []) {
      const label = labelOf(edge);
      const shift = label === "yes" ? -COLUMN / 2 : label === "no" ? COLUMN / 2 : 0;
      candidates.set(edge[1], [...(candidates.get(edge[1]) ?? []), x + shift]);
      depth.set(edge[1], Math.max(depth.get(edge[1]) ?? 0, (depth.get(id) ?? 0) + 1));
      incoming.set(edge[1], (incoming.get(edge[1]) ?? 1) - 1);
      if (incoming.get(edge[1]) === 0) queue.push(edge[1]);
    }
  }

  let row = Math.max(-1, ...[...positions.values()].map((p) => p.y / ROW)) + 1;
  for (const node of nodes) if (!positions.has(node.id)) positions.set(node.id, { x: 0, y: row++ * ROW });
  return positions;
}

/** Everything in a flow except the graph: the settings and stock rules. */
export function flowMeta(flow: FlowDoc): FlowMeta {
  return {
    supplier: flow.supplier,
    version: flow.version,
    login_path: flow.login_path,
    logged_in_url: flow.logged_in_url,
    blocked_if: flow.blocked_if,
    extract: flow.extract,
  };
}

/** Turns a flow into React Flow nodes and edges, with automatic positions. */
export function flowToGraph(flow: Pick<FlowDoc, "nodes" | "edges">): Graph {
  const positions = layout(flow.nodes, flow.edges);
  const nodes: GraphNode[] = flow.nodes.map((node) => ({
    id: node.id,
    type: "flowNode",
    position: positions.get(node.id) ?? { x: 0, y: 0 },
    data: { node },
  }));
  const edges = flow.edges.map((edge) => makeEdge(edge[0], edge[1], labelOf(edge)));
  return { nodes, edges };
}

/**
 * Turns the graph back into a flow. Nodes are listed in the order the edges lead (a Branch's yes
 * path before its no path), then any step that is not connected, so nothing is lost. Positions
 * are not saved because the server's flow format has no place for them.
 */
export function graphToFlow(graph: Graph, meta: FlowMeta): FlowDoc {
  const byId = new Map(graph.nodes.map((n) => [n.id, n.data.node]));
  const flowEdges: FlowEdge[] = graph.edges.map((e) => {
    const label = byId.get(e.source)?.type === "branch" ? e.sourceHandle : null;
    return label === "yes" || label === "no" ? [e.source, e.target, label] : [e.source, e.target];
  });

  const out = new Map<string, FlowEdge[]>();
  const hasIncoming = new Set<string>();
  for (const edge of flowEdges) {
    out.set(edge[0], [...(out.get(edge[0]) ?? []), edge]);
    hasIncoming.add(edge[1]);
  }
  const rank = (edge: FlowEdge) => (edge[2] === "yes" ? 0 : edge[2] === "no" ? 1 : 2);
  for (const [id, list] of out) out.set(id, [...list].sort((a, b) => rank(a) - rank(b)));

  const order: string[] = [];
  const seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id) || !byId.has(id)) return;
    seen.add(id);
    order.push(id);
    for (const edge of out.get(id) ?? []) visit(edge[1]);
  };
  graph.nodes.filter((n) => !hasIncoming.has(n.id)).forEach((n) => visit(n.id));
  graph.nodes.forEach((n) => visit(n.id));

  const position = new Map(order.map((id, index) => [id, index]));
  const edges = flowEdges
    .map((edge, index) => ({ edge, index }))
    .sort((a, b) => (position.get(a.edge[0]) ?? 0) - (position.get(b.edge[0]) ?? 0)
      || rank(a.edge) - rank(b.edge) || a.index - b.index)
    .map(({ edge }) => edge);
  return { ...meta, nodes: order.map((id) => byId.get(id) as FlowNode), edges };
}
