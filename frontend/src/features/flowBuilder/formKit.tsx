import { useContext, useEffect, useRef } from "react";
import type { FieldValues, UseFormReturn } from "react-hook-form";

import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { PickFlashContext } from "./pickFlash";

/** Calls `commit` with the form's values (and the field that changed) on every edit. */
export function useCommit<T extends FieldValues>(
  form: UseFormReturn<T>,
  commit: (values: Partial<T>, changed: string | undefined) => void,
): void {
  const latest = useRef(commit);
  useEffect(() => {
    latest.current = commit;
  });
  useEffect(() => {
    const subscription = form.watch((values, { name }) => latest.current(values as Partial<T>, name));
    return () => subscription.unsubscribe();
  }, [form]);
}

interface SelectorFieldProps {
  label: string;
  /** The form field name, which is also what Pick reports back. */
  field: string;
  picking: string | null;
  onPick: (field: string) => void;
  error?: string;
  inputProps: React.InputHTMLAttributes<HTMLInputElement>;
}

/** A text field for a selector, with a Pick button that waits for a click on the page snapshot. */
export function SelectorField({ label, field, picking, onPick, error, inputProps }: SelectorFieldProps) {
  const active = picking === field;
  const flash = useContext(PickFlashContext) === field;
  return (
    <div
      data-flash={flash ? "" : undefined}
      className={`flex items-end gap-2 rounded-control ${flash ? "bg-pill-positive ring-2 ring-positive" : ""}`}
    >
      <div className="min-w-0 flex-1">
        <TextField label={label} error={error} {...inputProps} />
      </div>
      <Button
        look="secondary"
        aria-label={`Pick selector for ${label}`}
        aria-pressed={active}
        onClick={() => onPick(field)}
        className={active ? "bg-active" : ""}
      >
        {active ? "Picking…" : "Pick"}
      </Button>
    </div>
  );
}
