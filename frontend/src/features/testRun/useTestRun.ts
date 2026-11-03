import { skipToken } from "@reduxjs/toolkit/query";
import { useRef, useState } from "react";

import { useStartTestRunMutation, useTestRunQuery } from "../../api/api";
import type { FlowDefinition, NewTestRun, TestRun, TestRunSnapshot } from "../../api/types";
import { startErrors as startErrorMessages } from "./plainWords";

export const POLL_MS = 1500;
const ACTIVE = new Set<TestRun["state"]>(["queued", "running", "waiting_for_code"]);

export interface StartOptions {
  mode: "login" | "extract";
  /** Stop after this node and take a snapshot there. */
  upToNodeId?: string;
  listingUrl?: string;
}

export interface TestRunController {
  /** The run being shown. It is always the latest one started, never an earlier one. */
  run: TestRun | null;
  /** The most recent snapshot, kept while later runs have none, so the picker stays usable. */
  snapshot: { runId: number; snapshot: TestRunSnapshot } | null;
  busy: boolean;
  startErrors: string[];
  pollError: boolean;
  start: (options: StartOptions) => void;
  retry: () => void;
}

/**
 * Starts Test runs and follows the latest one by polling until it finishes. Test runs never write to
 * Shopify. If two starts overlap, only the later one is shown: an earlier answer arriving late is
 * ignored, and the poll result is read per run id, so an old run can never replace a newer one.
 */
export function useTestRun(supplierId: number, getDraftFlow: () => FlowDefinition, pollMs = POLL_MS): TestRunController {
  const [startRun, { isLoading: starting }] = useStartTestRunMutation();
  const [runId, setRunId] = useState<number | null>(null);
  const [failedStart, setFailedStart] = useState<unknown>(null);
  const [finishedId, setFinishedId] = useState<number | null>(null);
  const [kept, setKept] = useState<TestRunController["snapshot"]>(null);
  const latestStart = useRef(0);

  const polling = runId !== null && finishedId !== runId;
  const {
    currentData: run,
    isError: pollError,
    refetch,
  } = useTestRunQuery(runId ?? skipToken, { pollingInterval: polling ? pollMs : 0 });

  // Derived during render, not in effects: stop polling once the run has finished, keep its snapshot.
  if (run && !ACTIVE.has(run.state) && finishedId !== run.id) setFinishedId(run.id);
  if (run?.snapshot && kept?.runId !== run.id) setKept({ runId: run.id, snapshot: run.snapshot });

  const start = ({ mode, upToNodeId, listingUrl }: StartOptions) => {
    const mine = ++latestStart.current;
    setFailedStart(null);
    const body: NewTestRun = {
      supplier_id: supplierId,
      flow: getDraftFlow(),
      mode,
      ...(upToNodeId ? { up_to_node_id: upToNodeId } : {}),
      ...(listingUrl ? { listing_url: listingUrl } : {}),
    };
    void startRun(body)
      .unwrap()
      .then(
        ({ id }) => {
          if (mine === latestStart.current) setRunId(id);
        },
        (error: unknown) => {
          if (mine === latestStart.current) setFailedStart(error);
        },
      );
  };

  const waitingForFirstRead = runId !== null && run === undefined && !pollError;
  return {
    run: run ?? null,
    snapshot: kept,
    busy: starting || (run !== undefined && ACTIVE.has(run.state)) || waitingForFirstRead,
    startErrors: failedStart === null ? [] : startErrorMessages(failedStart),
    pollError,
    start,
    retry: () => {
      if (runId !== null) void refetch();
    },
  };
}
