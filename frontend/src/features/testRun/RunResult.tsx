import type { TestRun } from "../../api/types";
import { Pill } from "../../components/ui/Pill";
import { loginResultText, stateText } from "./plainWords";
import { ReadingResult } from "./ReadingResult";
import { StepList } from "./StepList";

function StateMark({ state }: { state: TestRun["state"] }) {
  if (state === "waiting_for_code") return <Pill tone="warning">{stateText(state)}</Pill>;
  if (state === "failed") return <Pill tone="negative">{stateText(state)}</Pill>;
  return <span className="text-body font-medium">{stateText(state)}</span>;
}

/** One Test run: its state, what went wrong if anything, the steps and the reading. */
export function RunResult({ run }: { run: TestRun }) {
  const active = run.state === "queued" || run.state === "running" || run.state === "waiting_for_code";
  return (
    <div className="flex flex-col gap-3" aria-busy={active}>
      <StateMark state={run.state} />
      {run.state === "waiting_for_code" ? (
        <p className="text-body text-muted">Paste the code in the card at the top of the page. The run carries on when it arrives.</p>
      ) : null}
      {run.state === "failed" && run.error ? (
        <p role="alert" className="text-body text-negative">{run.error}</p>
      ) : null}
      {run.login_result ? <p className="text-body">Login: {loginResultText(run.login_result)}</p> : null}
      {run.steps.length > 0 ? <StepList steps={run.steps} /> : null}
      {run.reading ? <ReadingResult reading={run.reading} /> : null}
    </div>
  );
}
