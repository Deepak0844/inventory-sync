import type { ReactNode } from "react";

export interface TabSpec {
  id: string;
  label: string;
  panel: ReactNode;
}

/** Underlined tabs: the active one carries the 2px accent underline, nothing else is coloured. */
export function Tabs({ tabs, active, onChange }: { tabs: TabSpec[]; active: string; onChange: (id: string) => void }) {
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <div>
      <div role="tablist" className="mb-4 flex gap-4 overflow-x-auto border-b border-rule">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            id={`tab-${t.id}`}
            aria-selected={t.id === current.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => onChange(t.id)}
            className={`h-control whitespace-nowrap border-b-2 px-1 text-body max-md:h-touch ${
              t.id === current.id ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${current.id}`} aria-labelledby={`tab-${current.id}`}>
        {current.panel}
      </div>
    </div>
  );
}
