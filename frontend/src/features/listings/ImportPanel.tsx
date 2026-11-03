import { useState } from "react";

import { useImportListingsMutation } from "../../api/api";
import { Button } from "../../components/ui/Button";

/** CSV import: `sku,supplier,url[,selection_hint]`. Valid rows are applied even when others fail. */
export function ImportPanel({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [missing, setMissing] = useState(false);
  const [importFile, { data, isLoading, isError }] = useImportListingsMutation();

  function submit() {
    if (!file) return setMissing(true);
    setMissing(false);
    void importFile(file);
  }

  return (
    <section role="dialog" aria-label="Import listings" className="mb-4 rounded-card border bg-surface p-4">
      <h2 className="mb-1 text-section font-semibold">Import listings</h2>
      <p className="mb-3 text-muted">
        A CSV with the columns sku, supplier and url, and optionally selection_hint. The supplier is the Supplier&apos;s name.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-small font-medium text-muted">
          CSV file
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-body text-ink"
          />
        </label>
        <Button onClick={submit} disabled={isLoading}>Import</Button>
        <Button look="secondary" onClick={onClose}>Close</Button>
      </div>
      {missing ? <p className="mt-3 text-negative" role="alert">Choose a CSV file first.</p> : null}
      {isError ? <p className="mt-3 text-negative" role="alert">Couldn&apos;t import the file. Nothing was changed.</p> : null}
      {data ? (
        <div className="mt-3" aria-live="polite">
          <p className="font-medium">{`${data.created} created, ${data.updated} updated`}</p>
          {data.errors.length > 0 ? (
            <>
              <p className="mt-2 text-muted">{`${data.errors.length} ${data.errors.length === 1 ? "row was" : "rows were"} skipped:`}</p>
              <ul className="mt-1">
                {data.errors.map((e) => <li key={e.row}>{`Row ${e.row}: ${e.message}`}</li>)}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
