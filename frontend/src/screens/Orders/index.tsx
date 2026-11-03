import { useFlaggedOrdersQuery } from "../../api/api";
import type { FlaggedOrder } from "../../api/types";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { Pill } from "../../components/ui/Pill";
import { lastGood } from "../../features/listings/StatusMark";
import { reasonLabel } from "../../features/orders/reasons";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const MINUTE_MS = 60_000;

export default function Orders() {
  const { data, isLoading, isError, refetch, fulfilledTimeStamp } = useFlaggedOrdersQuery();
  const now = useNow(MINUTE_MS);
  const columns: Column<FlaggedOrder>[] = [
    { key: "name", header: "Order", cell: (o) => <span className="font-medium">{o.name}</span> },
    { key: "placed", header: "Placed", cell: (o) => ago(o.created_at, now) },
    {
      key: "reasons",
      header: "Why it is flagged",
      phone: "key",
      cell: (o) => (
        <span className="flex flex-wrap gap-1">
          {o.reasons.map((r) => <Pill key={r} tone={reasonLabel[r].tone}>{reasonLabel[r].text}</Pill>)}
        </span>
      ),
    },
    { key: "skus", header: "Variants", cell: (o) => (o.variants.length ? o.variants.map((v) => v.sku).join(", ") : null) },
  ];
  return (
    <>
      <h1 className="mb-1 text-title font-semibold">Orders to verify</h1>
      <p className="mb-4 text-muted">
        Check these with the Supplier before shipping. The system only flags orders: it never cancels orders or contacts customers.
      </p>
      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          rows={data ?? []}
          rowKey={(o) => o.order_id}
          total={data?.length ?? 0}
          noun="orders"
          empty="No orders need checking."
          loading={isLoading}
          error={isError ? `Couldn't load orders.${lastGood(fulfilledTimeStamp)}` : undefined}
          onRetry={refetch}
        />
      </div>
    </>
  );
}
