import type { FlowDoc } from "./types";

/** The login flow from docs/flow-nodes.md, valid under the server's rules. */
export function sampleFlow(): FlowDoc {
  return {
    supplier: "supplier-a",
    version: 1,
    login_path: "/login",
    logged_in_url: "https://supplier-a.example/account",
    blocked_if: { contains: "CAPTCHA" },
    nodes: [
      { id: "n1", type: "goto", url: "https://supplier-a.example/login" },
      { id: "n2", type: "fill", selector: "#email", value: "{{credentials.username}}" },
      { id: "n3", type: "fill", selector: "#password", value: "{{credentials.password}}", mask: true },
      { id: "n4", type: "click", selector: "button[type=submit]" },
      { id: "n5", type: "wait_for", selector: "#otp", role: "code_prompt", timeout_s: 5 },
      {
        id: "n6", type: "await_code", methods: ["ui_code", "email_code"],
        email: { sender: "no-reply@supplier-a.example", pattern: "(\\d{6})" }, timeout_s: 600,
      },
      { id: "n7", type: "fill", selector: "#otp", value: "{{code}}" },
      { id: "n8", type: "click", selector: "#verify" },
      { id: "n9", type: "wait_for", selector: ".account-menu", role: "logged_in_marker", timeout_s: 5 },
      { id: "n10", type: "save_session" },
    ],
    edges: [["n1", "n2"], ["n2", "n3"], ["n3", "n4"], ["n4", "n5"], ["n5", "n6"], ["n6", "n7"],
      ["n7", "n8"], ["n8", "n9"], ["n9", "n10"]],
    extract: {
      stock_selector: ".stock-status",
      in_stock_if: { contains: "In stock" },
      out_of_stock_if: { contains: "Out of stock" },
      quantity_selector: ".qty-left",
    },
  };
}

/** A flow where a Branch skips the code step for a trusted device. */
export function branchFlow(): FlowDoc {
  const base = sampleFlow();
  return {
    ...base,
    nodes: [
      base.nodes[0], base.nodes[1], base.nodes[2], base.nodes[3],
      { id: "b1", type: "branch", if_visible: "#otp" },
      base.nodes[5], base.nodes[6], base.nodes[7],
      base.nodes[8], base.nodes[9],
    ],
    edges: [["n1", "n2"], ["n2", "n3"], ["n3", "n4"], ["n4", "b1"], ["b1", "n6", "yes"],
      ["b1", "n9", "no"], ["n6", "n7"], ["n7", "n8"], ["n8", "n9"], ["n9", "n10"]],
  };
}
