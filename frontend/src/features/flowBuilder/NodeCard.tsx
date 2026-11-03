import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useContext } from "react";

import { NODE_LABELS, summary } from "./nodeInfo";
import { ProblemsContext } from "./problems";
import type { GraphNode } from "./types";

/** A step on the canvas: a plain card with its type as text and what it does underneath. */
export function NodeCard({ data, selected }: NodeProps<GraphNode>) {
  const node = data.node;
  const problem = useContext(ProblemsContext)[node.id]?.[0];
  const look = problem ? "border-negative" : selected ? "border-ink bg-active" : "";
  return (
    <div className={`w-reading rounded-card border bg-surface p-3 ${look}`}>
      <Handle type="target" position={Position.Top} />
      <p className="text-small font-semibold">{NODE_LABELS[node.type]}</p>
      <p className="break-words text-small text-muted">{summary(node)}</p>
      {problem ? <p className="mt-1 text-small text-negative">{problem}</p> : null}
      {node.type === "branch" ? (
        <div className="mt-2 flex justify-between text-small text-muted">
          <span>yes</span>
          <span>no</span>
          <Handle id="yes" type="source" position={Position.Bottom} style={{ left: "25%" }} />
          <Handle id="no" type="source" position={Position.Bottom} style={{ left: "75%" }} />
        </div>
      ) : (
        <Handle type="source" position={Position.Bottom} />
      )}
    </div>
  );
}
