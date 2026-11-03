import { useSettingsQuery } from "../../api/api";
import { BlockState } from "../../components/ui/BlockState";
import { SettingsForm } from "../../features/settings/SettingsForm";

/** Screen 11: "What are the system's rules?" */
export default function Settings() {
  const q = useSettingsQuery();
  return (
    <>
      <h1 className="mb-4 text-title font-semibold">Settings</h1>
      {q.isLoading ? <BlockState kind="loading" /> : null}
      {q.isError && !q.data ? (
        <BlockState kind="error" message="Couldn't load Settings." onRetry={() => void q.refetch()} />
      ) : null}
      {q.data ? <SettingsForm settings={q.data} /> : null}
    </>
  );
}
