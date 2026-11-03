import { useDeferredValue, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useVariantsQuery } from "../../api/api";
import type { VariantQuery, VariantRow } from "../../api/types";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { Pill } from "../../components/ui/Pill";
import { ReadingStrip } from "../../components/ui/ReadingStrip";
import { TextField } from "../../components/ui/TextField";
import { SelectField } from "../../features/listings/SelectField";
import { lastGood } from "../../features/listings/StatusMark";
import { usePagedQuery } from "../../features/listings/usePagedQuery";
import { ago } from "../../lib/format";
import { useNow } from "../../lib/useNow";

const PAGE_SIZE = 50;
const MINUTE_MS = 60_000;

export default function Variants() {
  // The top bar search sends people here as /variants?q=...
  const [params] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const q = useDeferredValue(search.trim());
  const [state, setState] = useState<VariantQuery["state"]>();
  const [staleOnly, setStaleOnly] = useState(false);
  const now = useNow(MINUTE_MS);
  const list = usePagedQuery<VariantRow, VariantQuery>(useVariantsQuery, {
    state,
    stale: staleOnly || undefined,
    q: q || undefined,
    limit: PAGE_SIZE,
  });

  const columns: Column<VariantRow>[] = [
    {
      key: "sku",
      header: "Variant",
      cell: (v) => (
        <>
          {v.sku}
          <span className="block text-small text-muted">{v.title}</span>
        </>
      ),
    },
    {
      key: "state",
      header: "State",
      phone: "key",
      cell: (v) => (
        <span className="flex flex-wrap items-center gap-1">
          {v.state === "sold_out" ? <Pill tone="negative">Sold out</Pill> : v.state === "available" ? <span className="text-muted">In stock</span> : null}
          {v.stale ? <Pill tone="warning">Stale</Pill> : null}
        </span>
      ),
    },
    { key: "since", header: "Sold out since", cell: (v) => (v.sold_out_at ? ago(v.sold_out_at, now) : null) },
    {
      key: "readings",
      header: "Recent readings",
      cell: (v) => <div className="w-reading max-w-full"><ReadingStrip readings={v.readings} /></div>,
    },
  ];

  return (
    <>
      <h1 className="mb-1 text-title font-semibold">Variants</h1>
      <p className="mb-4 text-muted">What is Sold Out, and since when. Two Out of Stock readings in a row make a Variant Sold Out.</p>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <TextField label="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <SelectField
          label="State"
          value={state ?? ""}
          onChange={(e) => setState(e.target.value === "" ? undefined : (e.target.value as VariantQuery["state"]))}
        >
          <option value="">All</option>
          <option value="available">In stock</option>
          <option value="sold_out">Sold out</option>
        </SelectField>
        <label className="flex h-control items-center gap-2 text-body max-md:h-touch">
          <input type="checkbox" checked={staleOnly} onChange={(e) => setStaleOnly(e.target.checked)} />
          Stale only
        </label>
      </div>
      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          rows={list.items}
          rowKey={(v) => v.id}
          total={list.total}
          noun="variants"
          empty="No variants match."
          loading={list.loading}
          error={list.error ? `Couldn't load variants.${lastGood(list.lastUpdated)}` : undefined}
          onRetry={list.retry}
          onLoadMore={list.loadMore}
        />
      </div>
    </>
  );
}
