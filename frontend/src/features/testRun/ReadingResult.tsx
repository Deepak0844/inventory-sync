import type { TestRunReading } from "../../api/types";
import { errorKindText, readingText } from "./plainWords";

const DASH = "–";

/** What the extract rules made of the Listing: the reading, the rule that matched, the quantity. */
export function ReadingResult({ reading }: { reading: TestRunReading }) {
  return (
    <div className="flex flex-col gap-1 rounded-control bg-raised p-3">
      <p className="text-section font-semibold">{readingText(reading.result)}</p>
      {reading.error_kind ? <p className="text-body">{errorKindText(reading.error_kind)}</p> : null}
      <p className="text-small text-muted">{reading.matched_rule ? `Matched rule: ${reading.matched_rule}` : "No rule matched."}</p>
      <p className="text-small text-muted">Quantity: {reading.quantity ?? DASH}</p>
    </div>
  );
}
