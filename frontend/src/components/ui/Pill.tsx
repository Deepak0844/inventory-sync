import type { ReactNode } from "react";

const tones = {
  negative: "bg-pill-negative text-pill-negative-ink",
  warning: "bg-pill-warning text-pill-warning-ink",
  positive: "bg-pill-positive text-pill-positive-ink",
  neutral: "bg-pill-neutral text-pill-neutral-ink",
} as const;

export type Tone = keyof typeof tones;

/** Status mark. Only things that need attention get one; healthy and In Stock stay unmarked. */
export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 text-small font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}
