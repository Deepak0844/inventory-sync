import type { ReactNode } from "react";

/** The white sheet inset from the frame. */
export function Sheet({ children }: { children: ReactNode }) {
  return (
    <main className="min-w-0 flex-1 overflow-y-auto rounded-sheet border bg-surface p-pad max-md:rounded-none max-md:border-0 max-md:p-4">
      {children}
    </main>
  );
}
