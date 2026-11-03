import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** A card with a title and, optionally, a "View all" link. Same look as the shared Card. */
export function Block({ title, viewAll, children }: { title: string; viewAll?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded-card border bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-section font-semibold">{title}</h2>
        {viewAll ? <Link to={viewAll} className="text-body text-accent hover:underline">View all</Link> : null}
      </div>
      {children}
    </section>
  );
}
