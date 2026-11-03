import { useState, type FormEvent } from "react";

import { usePendingCodesQuery, useSubmitCodeMutation } from "../../api/api";
import { mmss } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";

const POLL_MS = 5000;

/** The card at the top of every screen while a Supplier waits for a Login Code. */
export function NeedsCodePrompt() {
  const { data } = usePendingCodesQuery(undefined, { pollingInterval: POLL_MS });
  if (!data || data.length === 0) return null;
  return (
    <div className="mb-4 flex flex-col gap-3">
      {data.map((p) => (
        <CodeCard key={p.supplier_id} supplierId={p.supplier_id} name={p.supplier_name} expiresAt={p.expires_at} />
      ))}
    </div>
  );
}

function CodeCard(props: { supplierId: number; name: string; expiresAt: string }) {
  const [code, setCode] = useState("");
  const [submit, { isLoading, isError }] = useSubmitCodeMutation();
  const left = (Date.parse(props.expiresAt) - useNow()) / 1000;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = code.trim();
    if (trimmed) void submit({ supplierId: props.supplierId, code: trimmed }).then(() => setCode(""));
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3 rounded-card border bg-pill-warning p-4">
      <div className="mr-auto">
        <p className="font-semibold text-pill-warning-ink">{props.name} needs a code</p>
        <p className="text-small text-pill-warning-ink">{mmss(left)} left</p>
      </div>
      <TextField
        label="Login Code"
        inputMode="numeric"
        autoComplete="one-time-code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        error={isError ? "Couldn't send the code. Try again." : undefined}
      />
      <Button type="submit" disabled={isLoading}>Submit</Button>
    </form>
  );
}
