import { useState } from "react";

import { useApproveMutation, useRejectMutation } from "../../api/api";
import type { Approval, VariantState } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ago } from "../../lib/format";

const stateName = (s: VariantState) => (s === "sold_out" ? "Sold out" : s === "available" ? "In stock" : "Not managed");

/** One held batch. Approving asks first, because it writes to Shopify; rejecting only discards. */
export function ApprovalCard({ approval, now }: { approval: Approval; now: number }) {
  const [confirming, setConfirming] = useState(false);
  const [approve, approving] = useApproveMutation();
  const [reject, rejecting] = useRejectMutation();
  const n = approval.changes.length;
  const busy = approving.isLoading || rejecting.isLoading;

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-section font-semibold">{approval.supplier_name}</h2>
        <p className="text-muted">{ago(approval.created_at, now)}</p>
      </div>
      <ul className="mb-4">
        {approval.changes.map((c) => (
          <li key={c.variant_id} className="flex min-h-row items-center justify-between gap-3 border-t border-rule">
            <span>{c.sku}</span>
            <span className="text-muted">{`${stateName(c.from_state)} → ${stateName(c.to_state)}`}</span>
          </li>
        ))}
      </ul>
      {confirming ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-medium">{`Apply ${n} ${n === 1 ? "change" : "changes"} to Shopify?`}</p>
          <Button
            disabled={busy}
            onClick={() => void approve(approval.id).unwrap().catch(() => setConfirming(false))}
          >
            Yes, apply
          </Button>
          <Button look="secondary" disabled={busy} onClick={() => setConfirming(false)}>Cancel</Button>
        </div>
      ) : (
        <div className="flex gap-3">
          <Button disabled={busy} onClick={() => setConfirming(true)}>Approve</Button>
          <Button look="secondary" disabled={busy} onClick={() => void reject(approval.id)}>Reject</Button>
        </div>
      )}
      {approving.isError ? (
        <p className="mt-3 text-negative" role="alert">Couldn&apos;t approve this batch. Nothing was changed in Shopify.</p>
      ) : null}
      {rejecting.isError ? (
        <p className="mt-3 text-negative" role="alert">Couldn&apos;t reject this batch. Try again.</p>
      ) : null}
    </Card>
  );
}
