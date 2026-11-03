import { flowMeta, flowToGraph, graphToFlow } from "./convert";
import { branchFlow, sampleFlow } from "./testData";
import type { FlowDoc } from "./types";

const metaOf = flowMeta;
const pos = (flow: FlowDoc) => {
  const byId = new Map(flowToGraph(flow).nodes.map((n) => [n.id, n.position]));
  return (id: string) => byId.get(id)!;
};

describe("flowToGraph", () => {
  it("makes one graph node per flow node, carrying the node data", () => {
    const graph = flowToGraph(sampleFlow());
    expect(graph.nodes).toHaveLength(10);
    expect(graph.nodes[0]).toMatchObject({ id: "n1", type: "flowNode", data: { node: { type: "goto" } } });
  });

  it("makes one graph edge per flow edge and labels the branch paths", () => {
    const graph = flowToGraph(branchFlow());
    expect(graph.edges).toHaveLength(10);
    const yes = graph.edges.find((e) => e.source === "b1" && e.target === "n6")!;
    expect(yes).toMatchObject({ sourceHandle: "yes", label: "yes" });
    const plain = graph.edges.find((e) => e.source === "n1")!;
    expect(plain.sourceHandle).toBeUndefined();
  });

  it("lays a chain out top to bottom in one column", () => {
    const at = pos(sampleFlow());
    expect(at("n2").x).toBe(at("n1").x);
    expect(at("n2").y).toBeGreaterThan(at("n1").y);
    expect(at("n10").y).toBeGreaterThan(at("n9").y);
  });

  it("puts the yes path left of the no path, side by side", () => {
    const at = pos(branchFlow());
    expect(at("n6").x).toBeLessThan(at("n9").x);
    expect(at("n6").y).toBeGreaterThan(at("b1").y);
  });

  it("puts a join under the middle of the paths that meet there", () => {
    const at = pos(branchFlow());
    // n9 is reached from n8 (the yes side, left of the Branch) and from the Branch's no path.
    expect(at("n9").y).toBeGreaterThan(at("n8").y);
    expect(at("n9").x).toBe(at("b1").x);
  });

  it("places a step that is not connected to the first step off to the side", () => {
    const flow = sampleFlow();
    flow.nodes.push({ id: "x1", type: "click", selector: "#x" });
    const at = pos(flow);
    expect(at("x1").x).toBeGreaterThan(at("n1").x);
  });

  it("copes with a loop without hanging", () => {
    const flow = sampleFlow();
    flow.edges.push(["n10", "n2"]);
    expect(flowToGraph(flow).nodes).toHaveLength(10);
  });
});

describe("graphToFlow", () => {
  it.each([["a chain", sampleFlow()], ["a branch", branchFlow()]])("round-trips %s", (_name, flow) => {
    expect(graphToFlow(flowToGraph(flow), metaOf(flow))).toEqual(flow);
  });

  it("keeps the top-level fields and the extract rules", () => {
    const flow = sampleFlow();
    const out = graphToFlow(flowToGraph(flow), metaOf(flow));
    expect(out.login_path).toBe("/login");
    expect(out.blocked_if).toEqual({ contains: "CAPTCHA" });
    expect(out.extract.quantity_selector).toBe(".qty-left");
  });

  it("orders the nodes by following the edges, not by how they sit in the graph", () => {
    const flow = sampleFlow();
    const graph = flowToGraph(flow);
    graph.nodes.reverse();
    expect(graphToFlow(graph, metaOf(flow)).nodes.map((n) => n.id)).toEqual(flow.nodes.map((n) => n.id));
  });

  it("follows the yes path before the no path", () => {
    const flow = branchFlow();
    const ids = graphToFlow(flowToGraph(flow), metaOf(flow)).nodes.map((n) => n.id);
    expect(ids.indexOf("n6")).toBeLessThan(ids.indexOf("n9"));
  });

  it("keeps a step that is not connected, after the connected ones", () => {
    const flow = sampleFlow();
    const graph = flowToGraph(flow);
    graph.nodes.push({ id: "x1", type: "flowNode", position: { x: 0, y: 0 }, data: { node: { id: "x1", type: "save_session" } } });
    const out = graphToFlow(graph, metaOf(flow));
    expect(out.nodes.at(-1)?.id).toBe("x1");
  });

  it("writes a label only for edges that leave a Branch", () => {
    const flow = branchFlow();
    const graph = flowToGraph(flow);
    graph.edges[0] = { ...graph.edges[0], sourceHandle: "yes" };
    const out = graphToFlow(graph, metaOf(flow));
    expect(out.edges.find((e) => e[0] === "n1")).toEqual(["n1", "n2"]);
    expect(out.edges.filter((e) => e[0] === "b1")).toEqual([["b1", "n6", "yes"], ["b1", "n9", "no"]]);
  });

  it("does not store positions in the flow", () => {
    const flow = sampleFlow();
    expect(JSON.stringify(graphToFlow(flowToGraph(flow), metaOf(flow)))).not.toMatch(/position/);
  });
});
