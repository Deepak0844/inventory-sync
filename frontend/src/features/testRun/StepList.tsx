import { useState } from "react";

import type { TestRunStep } from "../../api/types";
import { Pill } from "../../components/ui/Pill";
import { stepName } from "./plainWords";

/** The steps a Test run took, in order, each with its screenshot a click away. */
export function StepList({ steps }: { steps: TestRunStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <ol className="flex list-decimal flex-col gap-3 pl-6">
      {steps.map((step, index) => {
        const shown = open === index;
        return (
          <li key={`${step.node_id}-${index}`} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-body">{stepName(step.type)}</span>
              <span className="text-small text-muted">{step.node_id}</span>
              {step.ok ? null : <Pill tone="negative">Failed</Pill>}
            </div>
            {step.error ? <p className="text-small text-negative">{step.error}</p> : null}
            {step.screenshot_url ? (
              <div className="flex flex-col items-start gap-2">
                <button
                  type="button"
                  aria-expanded={shown}
                  aria-label={`${shown ? "Hide" : "Show"} screenshot of step ${step.node_id}`}
                  onClick={() => setOpen(shown ? null : index)}
                  className="min-h-touch rounded-control text-small text-accent hover:underline"
                >
                  {shown ? "Hide screenshot" : <img src={step.screenshot_url} alt="" className="w-reading rounded-control border" />}
                </button>
                {shown ? (
                  <img src={step.screenshot_url} alt={`Screenshot after step ${step.node_id}`} className="w-full rounded-control border" />
                ) : null}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
