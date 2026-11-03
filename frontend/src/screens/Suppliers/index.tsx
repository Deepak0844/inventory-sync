import { useState } from "react";
import { Link } from "react-router-dom";

import { useSuppliersQuery } from "../../api/api";
import type { Supplier } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { Pill } from "../../components/ui/Pill";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { AddSupplierDialog } from "../../features/suppliers/AddSupplierDialog";
import { everyInterval } from "../../features/suppliers/format";
import { healthMark } from "../../features/suppliers/health";

const POLL_MS = 30_000;

/** Screen 2: "Which Suppliers are healthy?" */
export default function Suppliers() {
  const q = useSuppliersQuery(undefined, { pollingInterval: POLL_MS });
  const now = useNow(POLL_MS);
  const [adding, setAdding] = useState(false);

  const columns: Column<Supplier>[] = [
    {
      key: "name",
      header: "Supplier",
      cell: (s) => <Link to={`/suppliers/${s.id}`} className="font-medium hover:underline">{s.name}</Link>,
    },
    {
      key: "health",
      header: "Status",
      cell: (s) => {
        const mark = healthMark(s.health);
        return mark.tone ? <Pill tone={mark.tone}>{mark.label}</Pill> : <></>;
      },
    },
    { key: "last", header: "Last successful check", cell: (s) => (s.last_success_at ? ago(s.last_success_at, now) : null) },
    { key: "interval", header: "Interval", cell: (s) => everyInterval(s.interval_min) },
    { key: "listings", header: "Listings", numeric: true, cell: (s) => s.listing_count },
  ];

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-title font-semibold">Suppliers</h1>
        <Button onClick={() => setAdding(true)}>Add Supplier</Button>
      </div>
      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          rows={q.data ?? []}
          rowKey={(s) => s.id}
          total={q.data?.length ?? 0}
          noun="Suppliers"
          empty="No Suppliers yet. Add one to start checking stock."
          loading={q.isLoading}
          error={q.isError ? "Couldn't load Suppliers." : undefined}
          onRetry={() => void q.refetch()}
        />
      </div>
      {adding ? <AddSupplierDialog onClose={() => setAdding(false)} /> : null}
    </>
  );
}
