import type { FlowDefinition } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Card } from "../../components/ui/Card";
import { SelectorPicker } from "../selectorPicker";
import { TestRunPanel } from "./TestRunPanel";
import { POLL_MS, useTestRun } from "./useTestRun";

interface Props {
  supplierId: number;
  /** Read when a run starts, so a Test run always uses the flow as it is being edited. */
  getDraftFlow: () => FlowDefinition;
  /** The step selected in the editor, where a snapshot stops. */
  selectedNodeId: string | null;
  /** Called with the selector chosen by clicking the snapshot or typing it. */
  onPickSelector: (selector: string) => void;
  /** Skip text selectors, for the stock element whose text changes. */
  avoidText?: boolean;
  /** How often to ask for a running Test run; 1.5 s unless a test says otherwise. */
  pollIntervalMs?: number;
}

/** The flow builder's right-hand panel: run a Test run, then pick selectors from its snapshot. */
export function SelectorPanel({
  supplierId,
  getDraftFlow,
  selectedNodeId,
  onPickSelector,
  avoidText,
  pollIntervalMs = POLL_MS,
}: Props) {
  const controller = useTestRun(supplierId, getDraftFlow, pollIntervalMs);
  return (
    <div className="flex flex-col gap-gap">
      <TestRunPanel controller={controller} selectedNodeId={selectedNodeId} />
      <Card title="Pick a selector">
        {controller.snapshot ? (
          <SelectorPicker
            key={controller.snapshot.runId}
            snapshot={controller.snapshot.snapshot}
            onPick={onPickSelector}
            avoidText={avoidText}
          />
        ) : (
          <BlockState kind="empty" message="No snapshot yet. Select a step in the flow and choose Take snapshot here." />
        )}
      </Card>
    </div>
  );
}
