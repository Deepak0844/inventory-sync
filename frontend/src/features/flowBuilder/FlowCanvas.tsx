import "@xyflow/react/dist/style.css";
import "./flowBuilder.css";

import { Background, Controls, ReactFlow, useReactFlow, type Connection, type NodeTypes } from "@xyflow/react";
import type { DragEvent } from "react";

import type { Change, Draft } from "./builderState";
import { NodeCard } from "./NodeCard";
import { PALETTE_MIME } from "./nodeInfo";
import { ProblemsContext } from "./problems";
import type { NodeType } from "./types";

const nodeTypes: NodeTypes = { flowNode: NodeCard };

interface Props {
  draft: Draft;
  problems: Record<string, string[]>;
  /** On a phone the canvas can be panned and zoomed but not edited. */
  readOnly: boolean;
  onChange: (change: Change) => void;
  onAdd: (type: NodeType, position: { x: number; y: number }) => void;
}

/** The React Flow canvas. It shows the draft and reports every edit as a `Change`. */
export function FlowCanvas({ draft, problems, readOnly, onChange, onAdd }: Props) {
  const { screenToFlowPosition } = useReactFlow();

  const onDrop = (event: DragEvent) => {
    const type = event.dataTransfer.getData(PALETTE_MIME) as NodeType;
    if (!type || readOnly) return;
    event.preventDefault();
    onAdd(type, screenToFlowPosition({ x: event.clientX, y: event.clientY }));
  };
  const onConnect = (c: Connection) =>
    onChange({ kind: "connect", source: c.source, target: c.target, handle: c.sourceHandle });

  return (
    <ProblemsContext.Provider value={problems}>
      <div
        className="flow-canvas h-full w-full"
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <ReactFlow
          nodes={draft.graph.nodes}
          edges={draft.graph.edges}
          nodeTypes={nodeTypes}
          onNodesChange={(changes) => onChange({ kind: "nodes", changes })}
          onEdgesChange={(changes) => onChange({ kind: "edges", changes })}
          onConnect={onConnect}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          elementsSelectable={!readOnly}
          deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
          fitView
          // Start readable: a long flow is panned, not shrunk until the text is too small to read.
          fitViewOptions={{ minZoom: 0.7, maxZoom: 1, padding: 0.1 }}
          minZoom={0.3}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </ProblemsContext.Provider>
  );
}
