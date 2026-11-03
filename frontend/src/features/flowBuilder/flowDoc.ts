import type { FlowDoc } from "./types";

/** Reads what the server stored as a `FlowDoc`, filling in anything a half-written flow lacks. */
export function toFlowDoc(raw: Record<string, unknown>): FlowDoc {
  const r = raw as Partial<FlowDoc>;
  const e = r.extract;
  return {
    supplier: r.supplier ?? "",
    version: r.version ?? 1,
    login_path: r.login_path ?? "",
    logged_in_url: r.logged_in_url ?? "",
    blocked_if: { contains: r.blocked_if?.contains ?? "" },
    nodes: r.nodes ?? [],
    edges: r.edges ?? [],
    extract: {
      stock_selector: e?.stock_selector ?? "",
      in_stock_if: { contains: e?.in_stock_if?.contains ?? "" },
      out_of_stock_if: { contains: e?.out_of_stock_if?.contains ?? "" },
      ...(e?.quantity_selector !== undefined ? { quantity_selector: e.quantity_selector } : {}),
    },
  };
}

/**
 * The outline offered for a Supplier with no flow: open the login page, type the username and
 * password, submit, wait for the signed-in marker, save the session. The selectors are left empty
 * for the person to pick, because they depend on the Supplier's pages.
 */
export function starterFlow(supplier: { name: string; site_url: string }): FlowDoc {
  const base = supplier.site_url.replace(/\/+$/, "");
  return {
    supplier: supplier.name,
    version: 1,
    login_path: "/login",
    logged_in_url: `${base}/account`,
    blocked_if: { contains: "verify you are human" },
    nodes: [
      { id: "n1", type: "goto", url: `${base}/login` },
      { id: "n2", type: "fill", selector: "", value: "{{credentials.username}}" },
      { id: "n3", type: "fill", selector: "", value: "{{credentials.password}}", mask: true },
      { id: "n4", type: "click", selector: "" },
      { id: "n5", type: "wait_for", selector: "", role: "logged_in_marker", timeout_s: 5 },
      { id: "n6", type: "save_session" },
    ],
    edges: [["n1", "n2"], ["n2", "n3"], ["n3", "n4"], ["n4", "n5"], ["n5", "n6"]],
    extract: {
      stock_selector: "",
      in_stock_if: { contains: "In stock" },
      out_of_stock_if: { contains: "Out of stock" },
      quantity_selector: null,
    },
  };
}
