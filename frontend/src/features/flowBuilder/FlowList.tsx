import { Link } from "react-router-dom";

import { useFlowQuery, useSuppliersQuery } from "../../api/api";
import type { Supplier } from "../../api/types";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { Pill } from "../../components/ui/Pill";
import { toFlowDoc } from "./flowDoc";

function FlowStatus({ id }: { id: number }) {
  const q = useFlowQuery(id, { refetchOnMountOrArgChange: true });
  if (q.isLoading) return <span aria-busy="true" className="inline-block h-4 w-reading rounded-control bg-active" />;
  if (!q.data) return <Pill tone="warning">No flow yet</Pill>;
  const steps = toFlowDoc(q.data).nodes.length;
  return <span>{steps === 1 ? "1 step" : `${steps} steps`}</span>;
}

const columns: Column<Supplier>[] = [
  {
    key: "name",
    header: "Supplier",
    phone: "primary",
    cell: (s) => <Link to={`/flows/${s.id}`} className="font-medium hover:underline">{s.name}</Link>,
  },
  { key: "flow", header: "Flow", phone: "key", cell: (s) => <FlowStatus id={s.id} /> },
];

/** Screen 8, the list: pick a Supplier to open its flow in the builder. */
export function FlowList() {
  const q = useSuppliersQuery();
  const rows = q.data ?? [];
  return (
    <>
      <h1 className="mb-4 text-title font-semibold">Flows</h1>
      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(s) => s.id}
        total={rows.length}
        noun="Suppliers"
        empty="Add a Supplier first, then build its flow here."
        loading={q.isLoading}
        error={q.isError ? "Couldn't load Suppliers." : undefined}
        onRetry={() => void q.refetch()}
      />
    </>
  );
}
