import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useUpdateSupplierMutation } from "../../api/api";
import type { Supplier } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { CheckboxField, FormMessage } from "./fields";
import { WHOLE_NUMBER_MESSAGE } from "./format";

const whole = z.number({ invalid_type_error: WHOLE_NUMBER_MESSAGE }).int(WHOLE_NUMBER_MESSAGE).min(1, WHOLE_NUMBER_MESSAGE);
const schema = z.object({
  site_url: z.string().trim().url("Enter a full address, like https://supplier.example."),
  interval_min: whole,
  out_confirm_reads: whole,
  in_confirm_reads: whole,
  confirm_gap_min: whole,
  removed_as_unknown: z.boolean(),
  max_quantity: whole,
  code_window_min: whole,
});
type Values = z.infer<typeof schema>;

const pick = (s: Supplier): Values => ({
  site_url: s.site_url,
  interval_min: s.interval_min,
  out_confirm_reads: s.out_confirm_reads,
  in_confirm_reads: s.in_confirm_reads,
  confirm_gap_min: s.confirm_gap_min,
  removed_as_unknown: s.removed_as_unknown,
  max_quantity: s.max_quantity,
  code_window_min: s.code_window_min,
});

const FIELDS = [
  ["interval_min", "Check every (minutes)"],
  ["out_confirm_reads", "Out of Stock reads to confirm"],
  ["in_confirm_reads", "In Stock reads to confirm"],
  ["confirm_gap_min", "Minutes between confirmation reads"],
  ["max_quantity", "Maximum quantity"],
  ["code_window_min", "Login code window (minutes)"],
] as const;

/** The Supplier's own rules: how often to check, how many reads confirm a change, the quantity cap. */
export function SettingsTab({ supplier }: { supplier: Supplier }) {
  const [update, { isLoading, isError, isSuccess }] = useUpdateSupplierMutation();
  const { register, handleSubmit, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: pick(supplier),
  });
  const submit = handleSubmit(async (values) => {
    try {
      await update({ id: supplier.id, ...values }).unwrap();
    } catch {
      // isError drives the message
    }
  });

  return (
    <form onSubmit={submit} noValidate className="flex max-w-md flex-col gap-4">
      <TextField label="Site URL" type="url" error={errors.site_url?.message} {...register("site_url")} />
      {FIELDS.map(([name, label]) => (
        <TextField
          key={name}
          label={label}
          type="number"
          min={1}
          error={errors[name]?.message}
          {...register(name, { valueAsNumber: true })}
        />
      ))}
      <CheckboxField label="Treat a removed Listing as Unknown" {...register("removed_as_unknown")} />
      {isError ? <FormMessage kind="error">Couldn't save the settings. Try again.</FormMessage> : null}
      {isSuccess && !isLoading ? <FormMessage kind="ok">Settings saved.</FormMessage> : null}
      <div>
        <Button type="submit" disabled={isLoading}>Save settings</Button>
      </div>
    </form>
  );
}
