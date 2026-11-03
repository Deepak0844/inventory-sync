import { useApprovalsQuery } from "../../api/api";
import { BlockState } from "../../components/ui/BlockState";
import { ApprovalCard } from "../../features/approvals/ApprovalCard";
import { lastGood } from "../../features/listings/StatusMark";
import { useNow } from "../../lib/useNow";

const MINUTE_MS = 60_000;

export default function Approvals() {
  const { data, isLoading, isError, refetch, fulfilledTimeStamp } = useApprovalsQuery();
  const now = useNow(MINUTE_MS);
  return (
    <>
      <h1 className="mb-1 text-title font-semibold">Pending approvals</h1>
      <p className="mb-4 text-muted">
        These changes were held because too many Listings ran out at once. Nothing changes in Shopify until you approve.
      </p>
      {isLoading ? <BlockState kind="loading" /> : null}
      {isError ? (
        <BlockState kind="error" message={`Couldn't load approvals.${lastGood(fulfilledTimeStamp)}`} onRetry={refetch} />
      ) : null}
      {data && data.length === 0 ? <BlockState kind="empty" message="No changes are waiting for you." /> : null}
      <div className="flex flex-col gap-4">
        {(data ?? []).map((a) => <ApprovalCard key={a.id} approval={a} now={now} />)}
      </div>
    </>
  );
}
