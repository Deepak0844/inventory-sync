import type { ReadingResult } from "../../api/types";

const names: Record<ReadingResult, string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  unknown: "Unknown",
};
// ink = In Stock, red = Out of Stock, hollow = Unknown (so colour is never the only signal).
const looks: Record<ReadingResult, string> = {
  in_stock: "bg-ink",
  out_of_stock: "bg-negative",
  unknown: "border border-muted bg-surface",
};

/** A 2px track with one tick per reading, oldest first. Ticks are evenly spaced, not placed by time. */
export function ReadingStrip({ readings }: { readings: { result: ReadingResult; read_at: string }[] }) {
  if (readings.length === 0) return <span className="text-muted">–</span>;
  const label = `Last ${readings.length} readings: ${readings.map((r) => names[r.result]).join(", ")}`;
  return (
    <div role="img" aria-label={label} className="relative flex h-3 w-full items-center justify-between">
      <div className="absolute inset-x-0 h-track bg-border" />
      {readings.map((r) => (
        <span
          key={r.read_at}
          data-testid="tick"
          data-result={r.result}
          className={`relative h-3 w-tick ${looks[r.result]}`}
        />
      ))}
    </div>
  );
}
