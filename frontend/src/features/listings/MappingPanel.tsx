import { useDeferredValue, useState } from "react";

import { useMappingsQuery, useSetMappingsMutation, useVariantsQuery } from "../../api/api";
import type { Listing, Mapping, VariantRow } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { TextField } from "../../components/ui/TextField";
import { addMapping, moveMapping, removeMapping } from "./mappingOrder";
import { SelectField } from "./SelectField";

/** Pick a Variant, then set the priority order of the Listings it reads from. */
export function MappingPanel({ listings }: { listings: Listing[] }) {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [picked, setPicked] = useState<VariantRow | null>(null);
  const found = useVariantsQuery({ q, limit: 5 }, { skip: q === "" });

  return (
    <Card title="Mappings">
      <p className="mb-3 text-muted">
        A Variant reads from its Listings in priority order. It is Sold Out only when every Listing is out of stock.
      </p>
      <TextField label="Find a variant" value={search} onChange={(e) => setSearch(e.target.value)} />
      {found.isError ? <BlockState kind="error" message="Couldn't search variants." onRetry={found.refetch} /> : null}
      {found.data && found.data.items.length === 0 ? <BlockState kind="empty" message="No variants match." /> : null}
      <ul>
        {(found.data?.items ?? []).map((v) => (
          <li key={v.id} className="flex h-row items-center justify-between border-t border-rule">
            <span>{v.sku} <span className="text-muted">{v.title}</span></span>
            <Button look="text" aria-label={`Edit mapping for ${v.sku}`} onClick={() => setPicked(v)}>Edit mapping</Button>
          </li>
        ))}
      </ul>
      {picked ? <MappingEditor key={picked.id} variant={picked} listings={listings} /> : null}
    </Card>
  );
}

function MappingEditor({ variant, listings }: { variant: VariantRow; listings: Listing[] }) {
  const { data, isError, isLoading, refetch } = useMappingsQuery(variant.id);
  const [save, saving] = useSetMappingsMutation();
  const [draft, setDraft] = useState<Mapping[] | null>(null);
  const [toAdd, setToAdd] = useState("");

  const mappings = draft ?? [...(data ?? [])].sort((a, b) => a.priority - b.priority);
  const label = (id: number) => listings.find((l) => l.id === id)?.url ?? `Listing #${id}`;
  const mappable = listings.filter((l) => !mappings.some((m) => m.listing_id === l.id));

  return (
    <section aria-label={`Mapping for ${variant.sku}`} className="mt-4 border-t border-rule pt-4">
      <h3 className="mb-2 font-semibold">{`Mapping for ${variant.sku}`}</h3>
      {isLoading ? <BlockState kind="loading" /> : null}
      {isError ? <BlockState kind="error" message="Couldn't load this mapping." onRetry={refetch} /> : null}
      {data ? (
        <>
          {mappings.length === 0 ? <BlockState kind="empty" message="This variant has no Listings yet." /> : null}
          <ol>
            {mappings.map((m) => (
              <li key={m.listing_id} className="flex min-h-row items-center gap-3 border-t border-rule">
                <span className="w-4 text-right text-muted">{m.priority}</span>
                <span className="min-w-0 flex-1 break-all">{label(m.listing_id)}</span>
                <Button look="text" aria-label={`Move ${label(m.listing_id)} up`} onClick={() => setDraft(moveMapping(mappings, m.listing_id, "up"))}>Up</Button>
                <Button look="text" aria-label={`Move ${label(m.listing_id)} down`} onClick={() => setDraft(moveMapping(mappings, m.listing_id, "down"))}>Down</Button>
                <Button look="text" aria-label={`Remove ${label(m.listing_id)}`} onClick={() => setDraft(removeMapping(mappings, m.listing_id))}>Remove</Button>
              </li>
            ))}
          </ol>
          {mappable.length > 0 ? (
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <SelectField label="Add a Listing" value={toAdd} onChange={(e) => setToAdd(e.target.value)}>
                <option value="">Choose a Listing</option>
                {mappable.map((l) => <option key={l.id} value={l.id}>{l.url}</option>)}
              </SelectField>
              <Button look="secondary" disabled={toAdd === ""} onClick={() => { setDraft(addMapping(mappings, Number(toAdd))); setToAdd(""); }}>Add</Button>
            </div>
          ) : null}
          <div className="mt-4 flex items-center gap-3">
            <Button
              disabled={draft === null || saving.isLoading}
              onClick={() => void save({ id: variant.id, mappings }).unwrap().then(() => setDraft(null), () => undefined)}
            >
              Save mapping
            </Button>
            {saving.isError ? <p className="text-negative" role="alert">Couldn&apos;t save. The mapping is unchanged.</p> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
