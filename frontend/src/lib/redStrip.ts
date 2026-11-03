import type { RedStripEntry } from "../api/types";
import { ago } from "./format";

/** The sentence for the red strip, or null when no Supplier is overdue. The server decides who is overdue. */
export function describeRedStrip(entries: RedStripEntry[], now: number): string | null {
  if (entries.length === 0) return null;
  return entries
    .map((e) =>
      e.last_success_at
        ? `${e.supplier_name}: last successful check ${ago(e.last_success_at, now)}`
        : `${e.supplier_name}: no successful check yet`,
    )
    .join(". ");
}
