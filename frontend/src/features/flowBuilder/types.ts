import type { Edge, Node } from "@xyflow/react";

/** The flow definition JSON (docs/flow-nodes.md), narrowed from the loose API type. */
export interface Condition {
  contains: string;
}
export interface GotoNode {
  id: string;
  type: "goto";
  url: string;
}
export interface FillNode {
  id: string;
  type: "fill";
  selector: string;
  value: string;
  mask?: boolean;
}
export interface ClickNode {
  id: string;
  type: "click";
  selector: string;
}
export type WaitRole = "logged_in_marker" | "code_prompt";
export interface WaitForNode {
  id: string;
  type: "wait_for";
  selector: string;
  role?: WaitRole | null;
  timeout_s?: number;
}
export type CodeMethod = "ui_code" | "email_code";
export interface EmailRule {
  sender: string;
  pattern: string;
}
export interface AwaitCodeNode {
  id: string;
  type: "await_code";
  methods: CodeMethod[];
  email?: EmailRule | null;
  timeout_s?: number;
}
export interface BranchNode {
  id: string;
  type: "branch";
  if_visible: string;
}
export interface SaveSessionNode {
  id: string;
  type: "save_session";
}

export type FlowNode =
  | GotoNode | FillNode | ClickNode | WaitForNode | AwaitCodeNode | BranchNode | SaveSessionNode;
export type NodeType = FlowNode["type"];

export type EdgeLabel = "yes" | "no";
export type FlowEdge = [string, string] | [string, string, EdgeLabel];

export interface ExtractRules {
  stock_selector: string;
  in_stock_if: Condition;
  out_of_stock_if: Condition;
  quantity_selector?: string | null;
}

export interface FlowDoc {
  supplier: string;
  version: number;
  login_path: string;
  logged_in_url: string;
  blocked_if: Condition;
  nodes: FlowNode[];
  edges: FlowEdge[];
  extract: ExtractRules;
}
/** Everything in a flow except the graph itself. */
export type FlowMeta = Omit<FlowDoc, "nodes" | "edges">;

/** React Flow's view of a flow. Positions are laid out automatically and never saved. */
export type GraphNode = Node<{ node: FlowNode }, "flowNode">;
export type GraphEdge = Edge;
export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** What a check says is wrong: messages for the whole flow, and per node id. */
export interface Validation {
  flow: string[];
  nodes: Record<string, string[]>;
  ok: boolean;
}
