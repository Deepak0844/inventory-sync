import { useState } from "react";
import { useParams } from "react-router-dom";

import { useSupplierQuery } from "../../api/api";
import { BlockState } from "../../components/ui/BlockState";
import { Pill } from "../../components/ui/Pill";
import { FlowTab } from "../../features/suppliers/FlowTab";
import { healthMark } from "../../features/suppliers/health";
import { ListingsTab } from "../../features/suppliers/ListingsTab";
import { LoginTab } from "../../features/suppliers/LoginTab";
import { RunsTab } from "../../features/suppliers/RunsTab";
import { SettingsTab } from "../../features/suppliers/SettingsTab";
import { Tabs } from "../../features/suppliers/Tabs";

const POLL_MS = 15_000;

/** Screen 3: "What is wrong with this Supplier?" */
export default function SupplierDetail() {
  const id = Number(useParams().id);
  const q = useSupplierQuery(id, { pollingInterval: POLL_MS });
  const [tab, setTab] = useState("listings");

  if (q.isLoading) return <BlockState kind="loading" />;
  if (!q.data) {
    return <BlockState kind="error" message="Couldn't load this Supplier." onRetry={() => void q.refetch()} />;
  }
  const s = q.data;
  const mark = healthMark(s.health);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-title font-semibold">{s.name}</h1>
        {mark.tone ? <Pill tone={mark.tone}>{mark.label}</Pill> : null}
      </div>
      <p className="-mt-3 mb-4 text-body text-muted">{s.site_url}</p>
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "listings", label: "Listings", panel: <ListingsTab supplierId={s.id} /> },
          { id: "flow", label: "Flow", panel: <FlowTab supplierId={s.id} /> },
          { id: "login", label: "Login and 2FA", panel: <LoginTab supplier={s} /> },
          { id: "runs", label: "Runs", panel: <RunsTab supplierId={s.id} /> },
          { id: "settings", label: "Settings", panel: <SettingsTab supplier={s} /> },
        ]}
      />
    </>
  );
}
