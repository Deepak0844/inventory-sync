import type { FlowDefinition } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";

export interface SelectorColumnProps {
  supplierId: number;
  /** The flow as drafted now, including unsaved edits, for a Test run. */
  getDraftFlow: () => FlowDefinition;
  selectedNodeId: string | null;
  /** Called with the selector chosen from the page snapshot. */
  onPickSelector: (selector: string) => void;
  /** Where a pick will go, for example "Fill step, Selector"; null when no field is waiting. */
  targetLabel?: string | null;
}

/** The right-hand Test run and selector picker column. A stand-in until the real panel is wired in. */
export function SelectorColumn() {
  return <BlockState kind="empty" message="The Test run panel is loading." />;
}
