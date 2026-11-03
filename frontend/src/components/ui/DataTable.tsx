import type { ReactNode } from "react";

import { BlockState } from "./BlockState";
import { Button } from "./Button";

export interface Column<T> {
  key: string;
  header: string;
  numeric?: boolean;
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

/** 48px rows, right-aligned numbers, a grey dash for a missing value and a real zero as 0. */
export function DataTable<T>(p: Props<T>) {
  const align = (numeric?: boolean) => (numeric ? "text-right" : "text-left");
  const show = (v: ReactNode) => (v === null || v === undefined ? <span className="text-muted">–</span> : v);
  return (
    <div>
      <table className="w-full border-collapse text-body">
        <thead>
          <tr>
            {p.columns.map((c) => (
              <th key={c.key} className={`h-control px-3 text-small font-normal text-muted ${align(c.numeric)}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {p.loading
            ? Array.from({ length: SKELETON_ROWS }, (_, i) => (
                <tr key={i} data-testid="skeleton-row" className="h-row border-t border-rule">
                  {p.columns.map((c) => (
                    <td key={c.key} className="px-3"><div className="h-4 w-2/3 rounded-control bg-active" /></td>
                  ))}
                </tr>
              ))
            : p.rows.map((row) => (
                <tr key={p.rowKey(row)} className="h-row border-t border-rule">
                  {p.columns.map((c) => (
                    <td key={c.key} className="px-3">
                      <span className={`block ${align(c.numeric)}`}>{show(c.cell(row))}</span>
                    </td>
                  ))}
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
