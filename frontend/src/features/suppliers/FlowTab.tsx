import { useState } from "react";

import { useFlowQuery, useSetFlowMutation } from "../../api/api";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { FormMessage, TextArea } from "./fields";
import { flowErrors, parseFlowJson } from "./flowErrors";

/** Edits the flow as JSON. The visual editor arrives in Phase 6 and opens this same JSON. */
export function FlowTab({ supplierId }: { supplierId: number }) {
  const q = useFlowQuery(supplierId, { refetchOnMountOrArgChange: true });
  const [save, { isLoading }] = useSetFlowMutation();
  const [text, setText] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  const noFlowYet = (q.error as { status?: number } | undefined)?.status === 404;
  if (q.isLoading) return <BlockState kind="loading" />;
  if (q.isError && !noFlowYet) {
    return <BlockState kind="error" message="Couldn't load the flow." onRetry={() => void q.refetch()} />;
  }
  const value = text ?? (q.data ? JSON.stringify(q.data, null, 2) : "{}");

  const onSave = async () => {
    setSaved(false);
    const parsed = parseFlowJson(value);
    if (!parsed.ok) return setErrors([parsed.message]);
    try {
      await save({ id: supplierId, flow: parsed.value }).unwrap();
      setErrors([]);
      setSaved(true);
    } catch (error) {
      setErrors(flowErrors(error));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <TextArea
        label="Flow definition (JSON)"
        rows={22}
        value={value}
        onChange={(e) => {
          setText(e.target.value);
          setSaved(false);
        }}
      />
      {errors.map((message) => <FormMessage key={message} kind="error">{message}</FormMessage>)}
      {saved ? <FormMessage kind="ok">Flow saved.</FormMessage> : null}
      <div>
        <Button onClick={() => void onSave()} disabled={isLoading}>Save flow</Button>
      </div>
    </div>
  );
}
