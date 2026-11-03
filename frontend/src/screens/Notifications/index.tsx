import { useNotificationsQuery, useResolveNotificationMutation } from "../../api/api";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { Pill } from "../../components/ui/Pill";
import { lastGood } from "../../features/listings/StatusMark";
import { kindTitle, kindTone } from "../../features/notifications/kinds";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const MINUTE_MS = 60_000;

export default function Notifications() {
  const { data, isLoading, isError, refetch, fulfilledTimeStamp } = useNotificationsQuery({ resolved: false });
  const [resolve, resolving] = useResolveNotificationMutation();
  const now = useNow(MINUTE_MS);
  return (
    <>
      <h1 className="mb-1 text-title font-semibold">Notifications</h1>
      <p className="mb-4 text-muted">What needs fixing. Resolve an item once you have dealt with it.</p>
      {isLoading ? <BlockState kind="loading" /> : null}
      {isError ? (
        <BlockState kind="error" message={`Couldn't load notifications.${lastGood(fulfilledTimeStamp)}`} onRetry={refetch} />
      ) : null}
      {data && data.length === 0 ? <BlockState kind="empty" message="Nothing needs fixing." /> : null}
      {resolving.isError ? <p className="mb-3 text-negative" role="alert">Couldn&apos;t resolve that. Try again.</p> : null}
      <ul>
        {(data ?? []).map((n) => (
          <li key={n.id} className="flex flex-wrap items-start justify-between gap-3 border-t border-rule py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={kindTone(n.kind)}>{kindTitle(n.kind)}</Pill>
                {n.supplier_name ? <span className="font-medium">{n.supplier_name}</span> : null}
                <span className="text-muted">{ago(n.created_at, now)}</span>
              </div>
              <p className="mt-1">{n.message}</p>
              {n.screenshot_url ? (
                <a href={n.screenshot_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  View screenshot
                </a>
              ) : null}
            </div>
            <Button look="secondary" disabled={resolving.isLoading} onClick={() => void resolve(n.id)}>Resolve</Button>
          </li>
        ))}
      </ul>
    </>
  );
}
