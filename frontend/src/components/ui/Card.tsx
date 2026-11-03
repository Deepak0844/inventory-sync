import type { ReactNode } from "react";

/** The third nesting level: frame, sheet, card. A border, never a shadow. */
export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-card border bg-surface p-4">
      {title ? <h2 className="mb-3 text-section font-semibold">{title}</h2> : null}
      {children}
    </section>
  );
}
