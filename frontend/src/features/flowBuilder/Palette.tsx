import { NODE_LABELS, PALETTE_MIME, PALETTE_ORDER } from "./nodeInfo";
import type { NodeType } from "./types";

/** The step types that can be added, by click or by dragging onto the canvas. */
export function Palette({ onAdd }: { onAdd: (type: NodeType) => void }) {
  return (
    <ul className="flex flex-col gap-2">
      {PALETTE_ORDER.map((type) => (
        <li key={type}>
          <button
            type="button"
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(PALETTE_MIME, type);
              e.dataTransfer.effectAllowed = "move";
            }}
            onClick={() => onAdd(type)}
            className="h-control w-full rounded-control border bg-surface px-3 text-left text-body hover:bg-raised"
          >
            {NODE_LABELS[type]}
          </button>
        </li>
      ))}
      <li>
        <button
          type="button"
          disabled
          className="flex h-control w-full items-center justify-between rounded-control border px-3 text-left text-body text-muted"
        >
          <span>Code</span>
          <span className="text-small">coming later</span>
        </button>
      </li>
    </ul>
  );
}
