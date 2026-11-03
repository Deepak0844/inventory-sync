import { starterFlow, toFlowDoc } from "./flowDoc";
import { sampleFlow } from "./testData";
import { validateFlow } from "./validate";

describe("toFlowDoc", () => {
  it("keeps a complete flow as it is", () => {
    expect(toFlowDoc({ ...sampleFlow() })).toEqual(sampleFlow());
  });

  it("fills in what a half-written flow is missing instead of failing", () => {
    const doc = toFlowDoc({ supplier: "x" });
    expect(doc).toMatchObject({ supplier: "x", nodes: [], edges: [], login_path: "", blocked_if: { contains: "" } });
    expect(doc.extract.in_stock_if).toEqual({ contains: "" });
  });
});

describe("starterFlow", () => {
  const flow = starterFlow({ name: "Northline Supply", site_url: "https://northline.example" });

  it("opens the Supplier's login page and has the steps every login needs", () => {
    expect(flow.nodes[0]).toMatchObject({ type: "goto", url: "https://northline.example/login" });
    expect(flow.nodes.some((n) => n.type === "wait_for" && n.role === "logged_in_marker")).toBe(true);
    expect(flow.nodes.some((n) => n.type === "save_session")).toBe(true);
  });

  it("is a sound outline: only the selectors still need filling in", () => {
    const v = validateFlow(flow);
    expect(v.flow.filter((m) => /loop|connected|path|Save session|first step/i.test(m))).toEqual([]);
    expect(Object.values(v.nodes).flat().every((m) => /selector/i.test(m))).toBe(true);
  });

  it("does not double the slash when the site address ends with one", () => {
    expect(starterFlow({ name: "A", site_url: "https://a.example/" }).nodes[0]).toMatchObject({ url: "https://a.example/login" });
  });
});
