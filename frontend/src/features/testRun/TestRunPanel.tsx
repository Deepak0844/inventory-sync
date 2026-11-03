import { useState } from "react";

import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { TextField } from "../../components/ui/TextField";
import { RunResult } from "./RunResult";
import type { TestRunController } from "./useTestRun";

const FULL_ADDRESS = /^https?:\/\/\S+$/i;

interface Props {
  controller: TestRunController;
  /** The step selected in the flow, where "Take snapshot here" stops. */
  selectedNodeId: string | null;
}

/** The Test run controls and the result of the latest run. It never writes to Shopify, and says so. */
export function TestRunPanel({ controller, selectedNodeId }: Props) {
  const { run, busy, startErrors, pollError, start, retry } = controller;
  const [address, setAddress] = useState("");
  const listingUrl = address.trim();
  const addressOk = FULL_ADDRESS.test(listingUrl);

  return (
    <Card title="Test run">
      <div className="flex flex-col gap-4">
        <p className="text-small text-muted">Test runs never write to Shopify.</p>

        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => start({ mode: "login" })}>
            Run login test
          </Button>
          <Button
            look="secondary"
            disabled={busy || selectedNodeId === null}
            onClick={() => selectedNodeId && start({ mode: "login", upToNodeId: selectedNodeId })}
          >
            Take snapshot here
          </Button>
        </div>
        {selectedNodeId === null ? (
          <p className="text-small text-muted">Select a step in the flow to take a snapshot there.</p>
        ) : null}

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <TextField
              label="Listing address"
              value={address}
              placeholder="https://"
              onChange={(e) => setAddress(e.target.value)}
              className="w-full"
            />
          </div>
          <Button look="secondary" disabled={busy || !addressOk} onClick={() => start({ mode: "extract", listingUrl })}>
            Test on a Listing
          </Button>
        </div>
        {listingUrl !== "" && !addressOk ? (
          <p className="text-small text-muted">Enter the full address, starting with https://</p>
        ) : null}

        {startErrors.length > 0 ? (
          <ul role="alert" className="flex flex-col gap-1 text-body text-negative">
            {startErrors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}

        {pollError ? (
          <BlockState kind="error" message="Couldn't load the test run." onRetry={retry} />
        ) : run ? (
          <RunResult run={run} />
        ) : busy ? (
          <BlockState kind="loading" />
        ) : (
          <BlockState kind="empty" message="No test run yet. Run a login test, take a snapshot, or test a Listing." />
        )}
      </div>
    </Card>
  );
}
