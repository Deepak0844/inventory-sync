import type { FlowNode, NodeType } from "./types";

export const NODE_LABELS: Record<NodeType, string> = {
  goto: "Go to URL",
  fill: "Fill",
  click: "Click",
  wait_for: "Wait for",
  await_code: "Await code",
  branch: "Branch",
  save_session: "Save session",
};

/** The order steps are offered in, roughly the order a login uses them. */
export const PALETTE_ORDER: NodeType[] = [
  "goto", "fill", "click", "wait_for", "await_code", "branch", "save_session",
];

/** The mime type a palette button puts on a drag, so the canvas knows what was dropped. */
export const PALETTE_MIME = "application/x-flow-node";

const METHOD_NAMES = { ui_code: "dashboard", email_code: "mailbox" } as const;

/** One line saying what a step does, for its card. */
export function summary(node: FlowNode): string {
  switch (node.type) {
    case "goto":
      return node.url || "No address yet";
    case "fill":
    case "click":
      return node.selector || "No selector yet";
    case "wait_for": {
      const role = node.role === "logged_in_marker" ? " (logged-in marker)" : node.role === "code_prompt" ? " (code box)" : "";
      return `${node.selector || "No selector yet"}${role}`;
    }
    case "await_code":
      return node.methods.length > 0 ? `From the ${node.methods.map((m) => METHOD_NAMES[m]).join(" or ")}` : "No source chosen";
    case "branch":
      return node.if_visible ? `If ${node.if_visible} is visible` : "No element chosen";
    case "save_session":
      return "Keeps the login for the next run";
  }
}
