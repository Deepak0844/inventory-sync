import { useCheckSupplierMutation, useRunsQuery } from "../../api/api";
import type { Run } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const POLL_MS = 10_000;

/** Recent runs for the Supplier, and a button to check now. */
export function RunsTab({ supplierId }: { supplierId: number }) {
  const q = useRunsQuery(supplierId, { pollingInterval: POLL_MS });
  const [check, checking] = useCheckSupplierMutation();
  const now = useNow(POLL_MS);
  const items = q.data?.items ?? [];

  const columns: Column<Run>[] = [
    { key: "started", header: "Started", phone: "secondary", cell: (r) => ago(r.started_at, now) },
    { key: "kind", header: "Kind", phone: "primary", cell: (r) => r.kind },
    { key: "state", header: "State", phone: "key", cell: (r) => r.state },
    { key: "summary", header: "Summary", cell: (r) => r.summary || null },
  ];

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button look="secondary" onClick={() => void check(supplierId)} disabled={checking.isLoading}>Check now</Button>
      </div>
      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          rows={items}
          rowKey={(r) => r.id}
          total={items.length}
          noun="runs"
          empty="No runs yet."
          loading={q.isLoading}
          error={q.isError ? "Couldn't load runs." : undefined}
          onRetry={() => void q.refetch()}
        />
      </div>
    </div>
  );
}
