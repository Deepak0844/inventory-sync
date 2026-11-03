import type { FlowDoc, FlowNode, Validation } from "./types";

const VARIABLES = new Set(["credentials.username", "credentials.password", "code"]);
const PLACEHOLDER = /\{\{\s*([\w.]+)\s*\}\}/g;
const blank = (value: string | null | undefined) => !value || value.trim() === "";

/** Messages for one step's own fields. Wording is for the person editing, not the server. */
function nodeProblems(node: FlowNode): string[] {
  const problems: string[] = [];
  const needSelector = (value: string) => blank(value) && problems.push("Pick or enter a selector.");
  switch (node.type) {
    case "goto":
      if (blank(node.url)) problems.push("Enter the page address.");
      break;
    case "fill":
      needSelector(node.selector);
      if (blank(node.value)) problems.push("Enter the value to type.");
      for (const [, name] of node.value.matchAll(PLACEHOLDER)) {
        if (!VARIABLES.has(name)) {
          problems.push(`Unknown variable {{${name}}}. Use credentials.username, credentials.password or code.`);
        }
      }
      break;
    case "click":
      needSelector(node.selector);
      break;
    case "wait_for":
      needSelector(node.selector);
      if ((node.timeout_s ?? 0) < 0) problems.push("The wait time can't be negative.");
      break;
    case "await_code":
      if (node.methods.length === 0) problems.push("Choose at least one way to get the code.");
      if (node.methods.includes("email_code") && (blank(node.email?.sender) || blank(node.email?.pattern))) {
        problems.push("Add the sender and the pattern to find the code in the email.");
      }
      if ((node.timeout_s ?? 0) < 0) problems.push("The wait time can't be negative.");
      break;
    case "branch":
      needSelector(node.if_visible);
      break;
    case "save_session":
      break;
  }
  if (node.type !== "fill") {
    const text = Object.entries(node).filter(([key, v]) => key !== "id" && typeof v === "string");
    if (text.some(([, v]) => (v as string).includes("{{"))) problems.push("Variables only work in Fill steps.");
  }
  return problems;
}

/**
 * Checks a flow the way the server will, so mistakes show up before Save. Messages for a step
 * are keyed by its id; messages about the whole flow are listed apart.
 */
export function validateFlow(flow: FlowDoc): Validation {
  const flowMessages: string[] = [];
  const nodeMessages: Record<string, string[]> = {};
  const add = (id: string, message: string) => (nodeMessages[id] ??= []).push(message);

  const required: [string, string][] = [
    [flow.login_path, "Enter the login page path (for example /login)."],
    [flow.logged_in_url, "Enter the address of a page that only shows when signed in."],
    [flow.blocked_if.contains, "Enter the text that appears on a CAPTCHA or block page."],
    [flow.extract.stock_selector, "Pick the stock element in the stock rules."],
    [flow.extract.in_stock_if.contains, "Enter the text that means In stock."],
    [flow.extract.out_of_stock_if.contains, "Enter the text that means Out of stock."],
  ];
  for (const [value, message] of required) if (blank(value)) flowMessages.push(message);

  flow.nodes.forEach((node) => nodeProblems(node).forEach((m) => add(node.id, m)));

  const ids = flow.nodes.map((n) => n.id);
  const known = new Set(ids);
  for (const id of ids.filter((id, i) => ids.indexOf(id) !== i)) flowMessages.push(`Two steps have the same id (${id}).`);

  const edges = flow.edges.filter((e) => {
    const ok = known.has(e[0]) && known.has(e[1]);
    if (!ok) flowMessages.push(`A connection points at a step that doesn't exist (${known.has(e[0]) ? e[1] : e[0]}).`);
    return ok;
  });

  for (const node of flow.nodes) {
    const own = edges.filter((e) => e[0] === node.id);
    if (node.type === "branch") {
      const labels = own.map((e) => e[2] ?? "").sort();
      if (labels.join() !== "no,yes") add(node.id, "A Branch needs a yes path and a no path.");
    } else {
      if (own.some((e) => e[2])) add(node.id, "Only a Branch can have yes and no paths.");
      if (own.filter((e) => !e[2]).length > 1) add(node.id, "Only a Branch can lead to more than one step.");
    }
  }

  if (flow.nodes.length === 0) {
    flowMessages.push("Add a step to start the flow.");
  } else {
    checkShape(flow, edges, flowMessages, add);
  }
  if (!flow.nodes.some((n) => n.type === "save_session")) {
    flowMessages.push("Add a Save session step so the next run can skip the login.");
  }
  return { flow: flowMessages, nodes: nodeMessages, ok: flowMessages.length === 0 && Object.keys(nodeMessages).length === 0 };
}

/** Start, loops and the logged-in marker: the rules that need the whole graph. */
function checkShape(
  flow: FlowDoc,
  edges: FlowDoc["edges"],
  flowMessages: string[],
  add: (id: string, message: string) => void,
): void {
  const children = new Map<string, string[]>(flow.nodes.map((n) => [n.id, []]));
  const incoming = new Map<string, number>(flow.nodes.map((n) => [n.id, 0]));
  for (const [from, to] of edges) {
    children.get(from)?.push(to);
    incoming.set(to, (incoming.get(to) ?? 0) + 1);
  }
  const starts = flow.nodes.filter((n) => incoming.get(n.id) === 0);
  starts.slice(1).forEach((n) => add(n.id, "This step isn't connected to the first step."));

  const left = new Map(incoming);
  const queue = starts.map((n) => n.id);
  for (let at = 0; at < queue.length; at++) {
    for (const child of children.get(queue[at]) ?? []) {
      left.set(child, (left.get(child) ?? 1) - 1);
      if (left.get(child) === 0) queue.push(child);
    }
  }
  if (queue.length < flow.nodes.length) {
    flowMessages.push("The flow loops back on itself. Remove the connection that goes back.");
    return;
  }

  const isMarker = (id: string) => {
    const node = flow.nodes.find((n) => n.id === id);
    return node?.type === "wait_for" && node.role === "logged_in_marker";
  };
  if (!flow.nodes.some((n) => isMarker(n.id))) {
    flowMessages.push("Add a Wait for step with the role “logged-in marker”.");
    return;
  }
  // Walk every path once per (step, marker already seen) so a long flow stays cheap.
  const bad = new Set<string>();
  const seen = new Set<string>();
  const stack: [string, boolean][] = starts.slice(0, 1).map((n) => [n.id, false]);
  while (stack.length > 0) {
    const [id, passed] = stack.pop() as [string, boolean];
    const marker = passed || isMarker(id);
    if (seen.has(`${id}:${marker}`)) continue;
    seen.add(`${id}:${marker}`);
    const next = children.get(id) ?? [];
    if (next.length === 0 && !marker) bad.add(id);
    next.forEach((child) => stack.push([child, marker]));
  }
  if (bad.size > 0) {
    flowMessages.push("Every path must wait for the logged-in marker before it ends.");
    bad.forEach((id) => add(id, "This path ends without waiting for the logged-in marker."));
  }
}

/**
 * Shows the server's 422 messages in the builder: on the step they name (by id, or by position in
 * the list that was sent), otherwise on the whole flow.
 */
export function attachServerErrors(messages: string[], orderedIds: string[]): Validation {
  const flow: string[] = [];
  const nodes: Record<string, string[]> = {};
  const byLongest = [...orderedIds].sort((a, b) => b.length - a.length);
  for (const message of messages) {
    const position = /(?:^|\.)nodes\.(\d+)\b/.exec(message);
    let target = position ? orderedIds[Number(position[1])] : undefined;
    if (!target) {
      let best = Infinity;
      for (const id of byLongest) {
        const hit = new RegExp(`(^|[^\\w])${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w])`).exec(message);
        if (hit && hit.index < best) {
          best = hit.index;
          target = id;
        }
      }
    }
    if (target) (nodes[target] ??= []).push(message);
    else flow.push(message);
  }
  return { flow, nodes, ok: messages.length === 0 };
}
