import type { ReactNode } from "react";

import { BlockState } from "./BlockState";
import { Button } from "./Button";

/** Where a column goes in the two-line phone row: line 1 left, line 1 right, line 2, or not at all. */
export type PhoneRole = "primary" | "key" | "secondary" | "hidden";

export interface Column<T> {
  key: string;
  header: string;
  numeric?: boolean;
  /** Defaults to secondary, except the first column when no column declares a primary. */
  phone?: PhoneRole;
  cell: (row: T) => ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  total: number;
  noun: string;
  empty?: string;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  onLoadMore?: () => void;
}

const SKELETON_ROWS = 4;

// One DOM, restyled below the tablet breakpoint: the row becomes a wrapping flex line, the
// primary and key cells share line 1, a zero-height full-width break pushes the rest to line 2.
const ROW = "h-row border-t border-rule max-md:flex max-md:h-auto max-md:min-h-touch max-md:flex-wrap max-md:items-baseline max-md:gap-x-3 max-md:py-2";
const CELL: Record<PhoneRole, string> = {
  primary: "max-md:order-1 max-md:min-w-0 max-md:flex-1 max-md:overflow-hidden max-md:px-0",
  key: "max-md:order-2 max-md:shrink-0 max-md:px-0",
  secondary:
    "max-md:order-4 max-md:px-0 max-md:text-small max-md:text-muted max-md:before:mr-1 max-md:before:content-[attr(data-label)]",
  hidden: "max-md:hidden",
};

// Primary stays on one line; secondary reads "Label value" inline after its pseudo-element label.
const INNER: Record<PhoneRole, string> = {
  primary: "max-md:truncate",
  key: "",
  secondary: "max-md:inline",
  hidden: "",
};

function PhoneBreak() {
  return <td aria-hidden data-testid="phone-break" className="hidden p-0 max-md:order-3 max-md:block max-md:h-0 max-md:basis-full" />;
}

/** 48px rows, right-aligned numbers, a grey dash for a missing value and a real zero as 0. */
export function DataTable<T>(p: Props<T>) {
  const align = (numeric?: boolean) => (numeric ? "text-right" : "text-left");
  const missing = (v: ReactNode) => v === null || v === undefined;
  const show = (v: ReactNode) => (missing(v) ? <span className="text-muted">–</span> : v);
  const declaresPrimary = p.columns.some((c) => c.phone === "primary");
  const role = (c: Column<T>, i: number): PhoneRole =>
    c.phone ?? (i === 0 && !declaresPrimary ? "primary" : "secondary");
  return (
    <div>
      <table className="w-full border-collapse text-body max-md:block">
        <thead className="max-md:hidden">
          <tr>
            {p.columns.map((c) => (
              <th key={c.key} className={`h-control px-3 text-small font-normal text-muted ${align(c.numeric)}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="max-md:block">
          {p.loading
            ? Array.from({ length: SKELETON_ROWS }, (_, i) => (
                <tr key={i} data-testid="skeleton-row" className={ROW}>
                  {p.columns.map((c, ci) => (
                    <td key={c.key} data-phone={role(c, ci)} data-label={c.header} className={`px-3 ${CELL[role(c, ci)]}`}>
                      <div className="h-4 w-2/3 rounded-control bg-active" />
                    </td>
                  ))}
                  <PhoneBreak />
                </tr>
              ))
            : p.rows.map((row) => (
                <tr key={p.rowKey(row)} className={ROW}>
                  {p.columns.map((c, ci) => {
                    const r = role(c, ci);
                    const value = c.cell(row);
                    // A missing secondary value is left off the phone line rather than printing a dash.
                    const off = r === "secondary" && missing(value) ? " max-md:hidden" : "";
                    return (
                      <td
                        key={c.key}
                        data-phone={r}
                        data-label={r === "secondary" ? c.header : undefined}
                        className={`px-3 ${CELL[r]}${off}`}
                      >
                        <span className={`block ${align(c.numeric)} max-md:text-left ${INNER[r]}`}>{show(value)}</span>
                      </td>
                    );
                  })}
                  <PhoneBreak />
                </tr>
              ))}
        </tbody>
      </table>
      {p.error ? <BlockState kind="error" message={p.error} onRetry={p.onRetry} /> : null}
      {!p.loading && !p.error && p.rows.length === 0 ? (
        <BlockState kind="empty" message={p.empty ?? `No ${p.noun} yet.`} />
      ) : null}
      {!p.loading && !p.error && p.rows.length > 0 ? (
        <div className="flex items-center justify-between border-t border-rule pt-3 text-small text-muted">
          <span>{`${p.total.toLocaleString("en-US")} ${p.noun}`}</span>
          {p.onLoadMore && p.rows.length < p.total ? (
            <Button look="text" onClick={p.onLoadMore}>Load more</Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
