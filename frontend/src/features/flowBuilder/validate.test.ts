import { attachServerErrors, validateFlow } from "./validate";
import { branchFlow, sampleFlow } from "./testData";
import type { FlowDoc, FlowNode } from "./types";

const check = (mutate: (flow: FlowDoc) => void) => {
  const flow = sampleFlow();
  mutate(flow);
  return validateFlow(flow);
};
const node = <T extends FlowNode>(flow: FlowDoc, id: string) => flow.nodes.find((n) => n.id === id) as T;

describe("validateFlow", () => {
  it("accepts the documented login flow and a flow with a branch", () => {
    expect(validateFlow(sampleFlow())).toEqual({ flow: [], nodes: {}, ok: true });
    expect(validateFlow(branchFlow()).ok).toBe(true);
  });

  it("asks for a first step when the flow is empty", () => {
    const v = check((f) => {
      f.nodes = [];
      f.edges = [];
    });
    expect(v.flow.join(" ")).toMatch(/Add a step/);
  });

  it("flags a step that has no address, selector or value", () => {
    const v = check((f) => {
      node<FlowNode & { url: string }>(f, "n1").url = "";
      node<FlowNode & { selector: string }>(f, "n2").selector = " ";
      node<FlowNode & { value: string }>(f, "n3").value = "";
    });
    expect(v.nodes.n1[0]).toMatch(/address/);
    expect(v.nodes.n2[0]).toMatch(/selector/);
    expect(v.nodes.n3[0]).toMatch(/value/);
    expect(v.ok).toBe(false);
  });

  it("rejects an unknown variable and a variable outside Fill", () => {
    const v = check((f) => {
      node<FlowNode & { value: string }>(f, "n2").value = "{{credentials.usernam}}";
      node<FlowNode & { url: string }>(f, "n1").url = "https://x/?u={{code}}";
    });
    expect(v.nodes.n2[0]).toMatch(/credentials\.usernam/);
    expect(v.nodes.n1[0]).toMatch(/only work in Fill/i);
  });

  it("asks for at least one way to get the code, and the email details for email", () => {
    const none = check((f) => {
      node<FlowNode & { methods: string[] }>(f, "n6").methods = [];
    });
    expect(none.nodes.n6[0]).toMatch(/at least one/i);
    const noEmail = check((f) => {
      node<FlowNode & { email: unknown }>(f, "n6").email = null;
    });
    expect(noEmail.nodes.n6[0]).toMatch(/sender/);
  });

  it("does not ask for email details when only the dashboard code is used", () => {
    const v = check((f) => {
      const n = node<FlowNode & { methods: string[]; email: unknown }>(f, "n6");
      n.methods = ["ui_code"];
      n.email = null;
    });
    expect(v.ok).toBe(true);
  });

  it("requires the logged-in marker on every path", () => {
    const noMarker = check((f) => {
      node<FlowNode & { role: string | null }>(f, "n9").role = null;
    });
    expect(noMarker.flow.join(" ")).toMatch(/logged-in marker/);
    const v = validateFlow({
      ...branchFlow(),
      edges: [["n1", "n2"], ["n2", "n3"], ["n3", "n4"], ["n4", "b1"], ["b1", "n6", "yes"],
        ["b1", "n10", "no"], ["n6", "n7"], ["n7", "n8"], ["n8", "n9"], ["n9", "n10"]],
    });
    expect(v.nodes.n10.join(" ")).toMatch(/logged-in marker/);
  });

  it("requires a Save session step", () => {
    const v = check((f) => {
      f.nodes.pop();
      f.edges.pop();
    });
    expect(v.flow.join(" ")).toMatch(/Save session/);
  });

  it("flags a step with two ways forward unless it is a Branch", () => {
    const v = check((f) => f.edges.push(["n1", "n3"]));
    expect(v.nodes.n1.join(" ")).toMatch(/Branch/);
  });

  it("flags a Branch missing its yes or no path", () => {
    const flow = branchFlow();
    flow.edges = flow.edges.filter((e) => !(e[0] === "b1" && e[2] === "no"));
    expect(validateFlow(flow).nodes.b1.join(" ")).toMatch(/yes path and a no path/);
  });

  it("flags a yes/no label on a step that is not a Branch", () => {
    const v = check((f) => {
      f.edges[0] = ["n1", "n2", "yes"];
    });
    expect(v.nodes.n1.join(" ")).toMatch(/Only a Branch/);
  });

  it("flags a second first step and a loop", () => {
    const apart = check((f) => f.nodes.push({ id: "x1", type: "click", selector: "#x" }));
    expect(apart.nodes.x1.join(" ")).toMatch(/isn't connected/);
    const loop = check((f) => f.edges.push(["n10", "n2"]));
    expect(loop.flow.join(" ")).toMatch(/loops/);
  });

  it("flags an edge to a step that does not exist and a repeated id", () => {
    expect(check((f) => f.edges.push(["n10", "nope"])).flow.join(" ")).toMatch(/nope/);
    expect(check((f) => f.nodes.push({ id: "n1", type: "save_session" })).flow.join(" ")).toMatch(/same id/);
  });

  it("requires the page settings and the stock rules", () => {
    const v = check((f) => {
      f.login_path = "";
      f.logged_in_url = "";
      f.blocked_if.contains = "";
      f.extract.stock_selector = "";
      f.extract.in_stock_if.contains = "";
      f.extract.out_of_stock_if.contains = "";
    });
    expect(v.flow).toHaveLength(6);
  });

  it("does not require the quantity selector", () => {
    expect(check((f) => (f.extract.quantity_selector = null)).ok).toBe(true);
  });
});

describe("attachServerErrors", () => {
  const ids = ["n1", "n2", "n3"];

  it("puts a message that names a step on that step", () => {
    const out = attachServerErrors(["node n2 has more than one outgoing edge"], ids);
    expect(out.nodes.n2).toEqual(["node n2 has more than one outgoing edge"]);
    expect(out.flow).toEqual([]);
  });

  it("uses the position in the saved list when the message names one", () => {
    const out = attachServerErrors(["nodes.2.fill.value: unknown template variable credentials.x"], ids);
    expect(out.nodes.n3).toHaveLength(1);
  });

  it("keeps a message about the whole flow on the flow", () => {
    const out = attachServerErrors(["flow needs a wait_for node with role logged_in_marker"], ids);
    expect(out.flow).toHaveLength(1);
    expect(out.ok).toBe(false);
  });

  it("does not mistake an id inside another word", () => {
    const out = attachServerErrors(["an9 is not a node"], ["n9"]);
    expect(out.nodes.n9).toBeUndefined();
  });
});
