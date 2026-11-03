import { useDeferredValue, useState } from "react";

import { useListingsQuery, useSuppliersQuery } from "../../api/api";
import type { Listing, ListingQuery } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { TextField } from "../../components/ui/TextField";
import { ImportPanel } from "../../features/listings/ImportPanel";
import { MappingPanel } from "../../features/listings/MappingPanel";
import { SelectField } from "../../features/listings/SelectField";
import { lastGood, StatusMark } from "../../features/listings/StatusMark";
import { usePagedQuery } from "../../features/listings/usePagedQuery";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const PAGE_SIZE = 50;
const MINUTE_MS = 60_000;

export default function Listings() {
  const [supplierId, setSupplierId] = useState<number | undefined>();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [importing, setImporting] = useState(false);
  const now = useNow(MINUTE_MS);
  const suppliers = useSuppliersQuery();
  const list = usePagedQuery<Listing, ListingQuery>(useListingsQuery, {
    supplier_id: supplierId,
    q: q || undefined,
    limit: PAGE_SIZE,
  });
  const supplierName = (id: number) => suppliers.data?.find((s) => s.id === id)?.name;

  const columns: Column<Listing>[] = [
    {
      key: "url",
      header: "Listing",
      cell: (l) => (
        <>
          <a href={l.url} target="_blank" rel="noreferrer" className="break-all text-accent hover:underline">{l.url}</a>
          {l.selection_hint ? <span className="block text-small text-muted">{l.selection_hint}</span> : null}
        </>
      ),
    },
    { key: "supplier", header: "Supplier", cell: (l) => supplierName(l.supplier_id) },
    { key: "status", header: "Status", cell: (l) => <StatusMark listing={l} /> },
    { key: "quantity", header: "Quantity", numeric: true, cell: (l) => l.quantity },
    { key: "last", header: "Last success", cell: (l) => (l.last_success_at ? ago(l.last_success_at, now) : null) },
  ];

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-title font-semibold">Listings</h1>
        <Button onClick={() => setImporting(true)}>Import CSV</Button>
      </div>
      {importing ? <ImportPanel onClose={() => setImporting(false)} /> : null}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <SelectField
          label="Supplier"
          value={supplierId ?? ""}
          onChange={(e) => setSupplierId(e.target.value === "" ? undefined : Number(e.target.value))}
        >
          <option value="">All Suppliers</option>
          {(suppliers.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </SelectField>
        <TextField label="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="mb-6 overflow-x-auto">
        <DataTable
          columns={columns}
          rows={list.items}
          rowKey={(l) => l.id}
          total={list.total}
          noun="listings"
          empty="No listings yet. Import a CSV to add some."
          loading={list.loading}
          error={list.error ? `Couldn't load listings.${lastGood(list.lastUpdated)}` : undefined}
          onRetry={list.retry}
          onLoadMore={list.loadMore}
        />
      </div>
      <MappingPanel listings={list.items} />
    </>
  );
}
