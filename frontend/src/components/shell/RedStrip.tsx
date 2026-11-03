import type { RedStripEntry } from "../../api/types";
import { describeRedStrip } from "../../lib/redStrip";
import { useNow } from "../../lib/useNow";

/** Thin red strip across every screen when a Supplier has not succeeded for twice its interval. */
export function RedStrip({ entries }: { entries: RedStripEntry[] }) {
  const now = useNow(60_000);
  const text = describeRedStrip(entries, now);
  if (!text) return null;
  return (
    <div role="alert" className="flex min-h-strip items-center bg-negative px-4 text-small font-medium text-surface">
      {text}
    </div>
  );
}
