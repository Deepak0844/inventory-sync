import { Link } from "react-router-dom";

import { useOverviewQuery } from "../../api/api";
import type { Overview as OverviewData } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Pill } from "../../components/ui/Pill";
import { ago, clock } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { Block } from "../../features/overview/Block";
import { headline } from "../../features/overview/headline";
import { SoldOutChart } from "../../features/overview/SoldOutChart";
import { healthMark } from "../../features/suppliers/health";

const ROWS = 5;
const POLL_MS = 60_000;
const KPIS = [
  { key: "sold_out", label: "Sold Out" },
  { key: "in_stock", label: "In Stock" },
  { key: "stale", label: "Stale" },
  { key: "pending", label: "Pending" },
] as const;

const count = (n: number) => n.toLocaleString("en-US");

type Query = ReturnType<typeof useOverviewQuery>;

/** Error text that says what failed and when the data was last good. */
function failure(what: string, q: Query): string {
  const last = q.data ? ` Last updated ${clock(Date.parse(q.data.updated_at))}.` : "";
  return `Couldn't load ${what}.${last}`;
}

function Kpis({ q }: { q: Query }) {
  const data = q.data;
  return (
    <div role="group" aria-label="Stock counts" className="mb-6 grid grid-cols-2 gap-px overflow-hidden rounded-card border bg-border md:grid-cols-4">
      {q.isError && !data ? (
        <div className="col-span-full bg-surface p-4">
          <BlockState kind="error" message={failure("stock counts", q)} onRetry={() => void q.refetch()} />
        </div>
      ) : (
        KPIS.map(({ key, label }) => (
          <div key={key} className="bg-surface p-4">
            <dl>
              <dt className="text-small text-muted">{label}</dt>
              <dd className="mt-1 text-kpi font-semibold tabular-nums">
                {data ? (
                  <span className={key === "sold_out" && data.kpis.sold_out > 0 ? "text-negative" : ""}>
                    {count(data.kpis[key])}
                  </span>
                ) : (
                  <span data-testid="block-loading" className="block h-6 w-8 rounded-control bg-active" />
                )}
              </dd>
            </dl>
          </div>
        ))
      )}
    </div>
  );
}

function SupplierHealth({ data, now }: { data: OverviewData["suppliers"]; now: number }) {
  if (data.length === 0) return <BlockState kind="empty" message="No Suppliers yet. Add one to start checking stock." />;
  return (
    <ul>
      {data.slice(0, ROWS).map((s) => {
        const mark = healthMark(s.health);
        return (
          <li key={s.id} className="flex min-h-row items-center justify-between gap-3 border-t border-rule first:border-t-0">
            <div className="min-w-0">
              <Link to={`/suppliers/${s.id}`} className="block truncate text-body font-medium hover:underline">{s.name}</Link>
              <span className="text-small text-muted">
                {s.last_success_at ? `Checked ${ago(s.last_success_at, now)}` : "Not checked yet"}
              </span>
            </div>
            {mark.tone ? <Pill tone={mark.tone}>{mark.label}</Pill> : null}
          </li>
        );
      })}
    </ul>
  );
}

function RecentChanges({ data, now }: { data: OverviewData["recent_changes"]; now: number }) {
  if (data.length === 0) return <BlockState kind="empty" message="No changes yet." />;
  return (
    <ul>
      {data.slice(0, ROWS).map((c, i) => {
        const restored = c.from_state === "sold_out" && c.to_state === "available";
        return (
          <li key={`${c.sku}-${c.at}-${i}`} className="flex min-h-row items-center justify-between gap-3 border-t border-rule first:border-t-0">
            <div className="min-w-0">
              <span className="block truncate text-body font-medium">{c.sku}</span>
              <span className="text-small text-muted">{ago(c.at, now)}</span>
            </div>
            {c.to_state === "sold_out" ? (
              <Pill tone="negative">Sold out</Pill>
            ) : restored ? (
              <Pill tone="positive">Restored</Pill>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/** Screen 1: "Is my stock trustworthy right now?" */
export default function Overview() {
  const q = useOverviewQuery(undefined, { pollingInterval: POLL_MS });
  const now = useNow(POLL_MS);
  const data = q.data;
  const retry = () => void q.refetch();
  const loading = q.isLoading;
  const failed = q.isError && !data;

  return (
    <>
      <h1 className="text-title font-semibold">Overview</h1>
      <p className="mb-6 mt-1 min-h-6 text-section">
        {data ? headline(data.kpis.sold_out, data.suppliers) : null}
      </p>
      <Kpis q={q} />

      <div className="mb-6">
        <Block title="Sold Out variants per day">
          {loading ? <BlockState kind="loading" /> : failed ? (
            <BlockState kind="error" message={failure("the chart", q)} onRetry={retry} />
          ) : data && data.sold_out_by_day.length > 0 ? (
            <SoldOutChart days={data.sold_out_by_day} />
          ) : (
            <BlockState kind="empty" message="No Sold Out history yet." />
          )}
        </Block>
      </div>

      <div className="grid gap-gap md:grid-cols-2">
        <Block title="Supplier health" viewAll="/suppliers">
          {loading ? <BlockState kind="loading" /> : failed ? (
            <BlockState kind="error" message={failure("Supplier health", q)} onRetry={retry} />
          ) : data ? <SupplierHealth data={data.suppliers} now={now} /> : null}
        </Block>
        <Block title="Recent changes" viewAll="/variants">
          {loading ? <BlockState kind="loading" /> : failed ? (
            <BlockState kind="error" message={failure("recent changes", q)} onRetry={retry} />
          ) : data ? <RecentChanges data={data.recent_changes} now={now} /> : null}
        </Block>
      </div>
    </>
  );
}
