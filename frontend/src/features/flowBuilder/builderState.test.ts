import { applyChange, draftFromFlow, draftToFlow, newNode } from "./builderState";
import { branchFlow, sampleFlow } from "./testData";

const start = () => draftFromFlow(sampleFlow());
const ids = (d: ReturnType<typeof start>) => d.graph.nodes.map((n) => n.id);

describe("draft", () => {
  it("round-trips a flow", () => {
    expect(draftToFlow(start())).toEqual(sampleFlow());
  });
});

describe("newNode", () => {
  it("gives each node type usable defaults", () => {
    expect(newNode("wait_for", "n11")).toMatchObject({ id: "n11", type: "wait_for", selector: "" });
    expect(newNode("await_code", "n11")).toMatchObject({ methods: ["ui_code"], timeout_s: 600 });
    expect(newNode("fill", "n11")).toMatchObject({ selector: "", value: "" });
    expect(newNode("branch", "n11")).toMatchObject({ if_visible: "" });
  });
});

describe("add", () => {
  it("adds a node with a fresh id and selects it", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "click", position: { x: 5, y: 6 } });
    expect(ids(d).at(-1)).toBe("n11");
    expect(d.graph.nodes.at(-1)).toMatchObject({ selected: true, position: { x: 5, y: 6 } });
    expect(d.graph.nodes.filter((n) => n.selected)).toHaveLength(1);
  });

  it("picks the next free id and keeps ids unique", () => {
    let d = applyChange(start(), { kind: "remove", id: "n10" });
    d = applyChange(d, { kind: "add", nodeType: "save_session", position: { x: 0, y: 0 } });
    expect(ids(d).at(-1)).toBe("n10");
    d = applyChange(d, { kind: "add", nodeType: "click", position: { x: 0, y: 0 } });
    expect(new Set(ids(d)).size).toBe(ids(d).length);
  });

  it("connects the new step after a step that has nothing after it", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "click", position: { x: 0, y: 0 }, after: "n10" });
    expect(draftToFlow(d).edges.at(-1)).toEqual(["n10", "n11"]);
  });

  it("inserts the new step between the chosen step and the one that followed it", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "click", position: { x: 0, y: 0 }, after: "n1" });
    const edges = draftToFlow(d).edges;
    expect(edges).toContainEqual(["n1", "n11"]);
    expect(edges).toContainEqual(["n11", "n2"]);
    expect(edges).not.toContainEqual(["n1", "n2"]);
  });

  it("inserts a Branch so that skipping it ('no') carries on to the next step", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "branch", position: { x: 0, y: 0 }, after: "n1" });
    const edges = draftToFlow(d).edges;
    expect(edges).toContainEqual(["n1", "n11"]);
    expect(edges).toContainEqual(["n11", "n2", "no"]);
    expect(edges.some((e) => e[0] === "n11" && e[2] === "yes")).toBe(false);
  });

  it("draws an inserted step between its neighbours, not at the bottom of the canvas", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "click", position: { x: 0, y: 9999 }, after: "n1" });
    const y = (id: string) => d.graph.nodes.find((n) => n.id === id)!.position.y;
    expect(y("n1")).toBeLessThan(y("n11"));
    expect(y("n11")).toBeLessThan(y("n2"));
  });

  it("keeps the inserted step selected", () => {
    const d = applyChange(start(), { kind: "add", nodeType: "click", position: { x: 0, y: 0 }, after: "n1" });
    expect(d.graph.nodes.filter((n) => n.selected).map((n) => n.id)).toEqual(["n11"]);
  });

  it("puts a step added after that Branch on its free path and rejoins the main line", () => {
    let d = applyChange(start(), { kind: "add", nodeType: "branch", position: { x: 0, y: 0 }, after: "n1" });
    d = applyChange(d, { kind: "add", nodeType: "click", position: { x: 0, y: 0 }, after: "n11" });
    const edges = draftToFlow(d).edges;
    expect(edges).toContainEqual(["n11", "n12", "yes"]);
    expect(edges).toContainEqual(["n12", "n2"]);
  });

  it("connects after a Branch to its first free path", () => {
    const flow = branchFlow();
    flow.edges = flow.edges.filter((e) => !(e[0] === "b1" && e[2] === "no"));
    const d = applyChange(draftFromFlow(flow), { kind: "add", nodeType: "click", position: { x: 0, y: 0 }, after: "b1" });
    expect(draftToFlow(d).edges).toContainEqual(["b1", "n11", "no"]);
  });
});

describe("update and remove", () => {
  it("replaces a node's data", () => {
    const d = applyChange(start(), { kind: "update", node: { id: "n1", type: "goto", url: "https://new" } });
    expect(draftToFlow(d).nodes[0]).toEqual({ id: "n1", type: "goto", url: "https://new" });
  });

  it("removes a node and every connection to it", () => {
    const d = applyChange(start(), { kind: "remove", id: "n5" });
    expect(ids(d)).not.toContain("n5");
    expect(d.graph.edges.some((e) => e.source === "n5" || e.target === "n5")).toBe(false);
  });
});

describe("connect", () => {
  it("replaces the one way forward of a step that is not a Branch", () => {
    const d = applyChange(start(), { kind: "connect", source: "n1", target: "n3" });
    expect(draftToFlow(d).edges.filter((e) => e[0] === "n1")).toEqual([["n1", "n3"]]);
  });

  it("replaces only the path with the same label on a Branch", () => {
    const d = applyChange(draftFromFlow(branchFlow()), { kind: "connect", source: "b1", target: "n7", handle: "yes" });
    expect(draftToFlow(d).edges.filter((e) => e[0] === "b1")).toEqual([["b1", "n7", "yes"], ["b1", "n9", "no"]]);
  });

  it("ignores a step connected to itself and an exact repeat", () => {
    const before = start();
    expect(applyChange(before, { kind: "connect", source: "n1", target: "n1" })).toBe(before);
    expect(applyChange(before, { kind: "connect", source: "n1", target: "n2" }).graph.edges).toHaveLength(9);
  });
});

describe("settings", () => {
  it("changes the top-level fields and the stock rules without touching the graph", () => {
    let d = applyChange(start(), { kind: "meta", patch: { login_path: "/signin" } });
    d = applyChange(d, { kind: "extract", patch: { stock_selector: "#s" } });
    const flow = draftToFlow(d);
    expect(flow.login_path).toBe("/signin");
    expect(flow.extract.stock_selector).toBe("#s");
    expect(flow.nodes).toEqual(sampleFlow().nodes);
  });

  it("replaces everything when a saved flow is loaded again", () => {
    const d = applyChange(applyChange(start(), { kind: "remove", id: "n1" }), { kind: "replace", flow: sampleFlow() });
    expect(draftToFlow(d)).toEqual(sampleFlow());
  });
});
