import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { BlockState } from "../../components/ui/BlockState";
import { FlowBuilder } from "../../features/flowBuilder/FlowBuilder";
import { SelectorPanel } from "../../features/testRun";
import { FlowList } from "../../features/flowBuilder/FlowList";

function Builder() {
  const id = Number(useParams().supplierId);
  if (!Number.isInteger(id) || id < 1) return <BlockState kind="empty" message="That isn't a Supplier." />;
  return <FlowBuilder supplierId={id} SelectorPanel={SelectorPanel} />;
}

/** Screen 8: the list of flows at /flows, and the visual builder at /flows/:supplierId. */
export default function Flows() {
  return (
    <Routes>
      <Route index element={<FlowList />} />
      <Route path=":supplierId" element={<Builder />} />
      <Route path="*" element={<Navigate to="/flows" replace />} />
    </Routes>
  );
}
