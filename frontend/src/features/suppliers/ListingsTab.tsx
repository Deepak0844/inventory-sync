import { useState } from "react";

import { useListingsQuery } from "../../api/api";
import type { Listing, ReadingResult } from "../../api/types";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { Pill } from "../../components/ui/Pill";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const PAGE = 50;

const status: Record<ReadingResult, { label: string; tone: "negative" | "neutral" | null }> = {
  in_stock: { label: "In stock", tone: null },
  out_of_stock: { label: "Out of stock", tone: "negative" },
  unknown: { label: "Unknown", tone: "neutral" },
};

/** The Supplier's Listings, using the same query as the Listings screen. */
export function ListingsTab({ supplierId }: { supplierId: number }) {
  const [limit, setLimit] = useState(PAGE);
  const q = useListingsQuery({ supplier_id: supplierId, limit });
  const now = useNow(60_000);

  const columns: Column<Listing>[] = [
    { key: "url", header: "Listing", cell: (l) => <span className="block max-w-xs truncate">{l.url}</span> },
    { key: "hint", header: "Variant hint", cell: (l) => l.selection_hint },
    {
      key: "status",
      header: "Stock",
      cell: (l) => {
        const s = status[l.status];
        return (
          <span className="flex gap-1">
            {s.tone ? <Pill tone={s.tone}>{s.label}</Pill> : s.label}
            {l.removed ? <Pill tone="warning">Removed</Pill> : null}
          </span>
        );
      },
    },
    { key: "qty", header: "Quantity", numeric: true, cell: (l) => l.quantity },
    { key: "last", header: "Last read", cell: (l) => (l.last_success_at ? ago(l.last_success_at, now) : null) },
  ];

  return (
    <div className="overflow-x-auto">
      <DataTable
        columns={columns}
        rows={q.data?.items ?? []}
        rowKey={(l) => l.id}
        total={q.data?.total ?? 0}
        noun="Listings"
        empty="No Listings yet. Import a CSV on the Listings screen."
        loading={q.isLoading}
        error={q.isError ? "Couldn't load Listings." : undefined}
        onRetry={() => void q.refetch()}
        onLoadMore={() => setLimit((n) => n + PAGE)}
      />
    </div>
  );
}
