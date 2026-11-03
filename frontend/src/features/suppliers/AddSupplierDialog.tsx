import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAddSupplierMutation } from "../../api/api";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { CheckboxField, FormMessage } from "./fields";
import { WHOLE_NUMBER_MESSAGE } from "./format";

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name."),
  site_url: z.string().url("Enter a full address, like https://supplier.example."),
  interval_min: z.number({ invalid_type_error: WHOLE_NUMBER_MESSAGE }).int(WHOLE_NUMBER_MESSAGE).min(1, WHOLE_NUMBER_MESSAGE),
  two_fa_methods: z.array(z.enum(["ui_code", "email_code"])),
});
type Values = z.infer<typeof schema>;

const DEFAULT_INTERVAL_MIN = 180;

/** Modal form for a new Supplier. Credentials and the flow are added on its own page afterwards. */
export function AddSupplierDialog({ onClose }: { onClose: () => void }) {
  const [add, { isLoading, isError }] = useAddSupplierMutation();
  const { register, handleSubmit, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", site_url: "", interval_min: DEFAULT_INTERVAL_MIN, two_fa_methods: ["ui_code"] },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = handleSubmit(async (values) => {
    try {
      await add(values).unwrap();
      onClose();
    } catch {
      // the mutation's isError drives the message below
    }
  });

  return (
    <div className="fixed inset-0 z-10 flex items-start justify-center p-4 md:items-center">
      <div className="absolute inset-0 bg-ink opacity-30" onClick={onClose} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-labelledby="add-supplier-title" className="relative w-full max-w-md rounded-sheet border bg-surface p-6">
        <h2 id="add-supplier-title" className="mb-4 text-section font-semibold">Add Supplier</h2>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <TextField label="Name" autoFocus error={errors.name?.message} {...register("name")} />
          <TextField label="Site URL" type="url" error={errors.site_url?.message} {...register("site_url")} />
          <TextField
            label="Check every (minutes)"
            type="number"
            min={1}
            error={errors.interval_min?.message}
            {...register("interval_min", { valueAsNumber: true })}
          />
          <fieldset className="flex flex-col">
            <legend className="mb-1 text-small font-medium text-muted">Login code methods</legend>
            <CheckboxField label="Pasted code" value="ui_code" {...register("two_fa_methods")} />
            <CheckboxField label="Mailbox code" value="email_code" {...register("two_fa_methods")} />
          </fieldset>
          {isError ? <FormMessage kind="error">Couldn't add the Supplier. Check the details and try again.</FormMessage> : null}
          <div className="flex justify-end gap-2">
            <Button look="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isLoading}>Create Supplier</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
