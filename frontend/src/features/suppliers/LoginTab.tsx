import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  useCancelManualLoginMutation, useCredentialsQuery, useManualLoginStatusQuery,
  useRetrySupplierMutation, useSetCredentialsMutation, useStartLoginMutation,
  useStartManualLoginMutation,
} from "../../api/api";
import type { ManualLogin, Supplier } from "../../api/types";
import { BlockState } from "../../components/ui/BlockState";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/TextField";
import { FormMessage } from "./fields";
import { sessionAge } from "./format";

const schema = z.object({
  username: z.string().trim().min(1, "Enter the username."),
  password: z.string().min(1, "Enter the password."),
});
type Values = z.infer<typeof schema>;

const METHOD_NAMES = { ui_code: "Pasted code", email_code: "Mailbox code" } as const;

const OPEN_STATES = new Set<ManualLogin["state"]>(["queued", "ready"]);

function ManualLoginControl({ supplierId }: { supplierId: number }) {
  const status = useManualLoginStatusQuery(supplierId, {
    pollingInterval: 3_000,
    skipPollingIfUnfocused: true,
  });
  const [start, starting] = useStartManualLoginMutation();
  const [cancel, cancelling] = useCancelManualLoginMutation();
  const attempt = status.data?.session;

  if (!status.data?.enabled) return null;

  const canStart = !attempt || !OPEN_STATES.has(attempt.state);
  const failed = attempt?.state === "failed" || attempt?.state === "expired";
  return (
    <div className="mt-2 flex flex-col gap-3 border-t border-rule pt-4">
      <div>
        <h3 className="text-body font-semibold">Private browser</h3>
        <p className="mt-1 text-small text-muted">
          Use this only when the Supplier asks you to complete a CAPTCHA or login yourself.
        </p>
      </div>
      {attempt?.state === "queued" ? <p role="status" className="text-small">Starting private browser…</p> : null}
      {attempt?.state === "ready" ? (
        <div className="flex flex-col gap-2">
          <p role="status" className="text-small">
            Browser ready. Make sure your SSH tunnel is open, then finish the login before this session expires.
          </p>
          <div className="flex flex-wrap gap-2">
            <a
              href={attempt.browser_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-control min-w-touch items-center justify-center rounded-control bg-ink px-3 text-body font-medium text-surface hover:opacity-90 max-md:h-touch"
            >
              Open private browser
            </a>
            <Button
              look="secondary"
              disabled={cancelling.isLoading}
              onClick={() => void cancel(supplierId)}
            >
              Cancel manual login
            </Button>
          </div>
        </div>
      ) : null}
      {attempt?.state === "succeeded" ? (
        <FormMessage kind="ok">Manual login saved. Scheduled runs can reuse this session.</FormMessage>
      ) : null}
      {failed ? (
        <FormMessage kind="error">
          {attempt.error || (attempt.state === "expired" ? "The manual login expired." : "The manual login failed.")}
        </FormMessage>
      ) : null}
      {starting.isError || cancelling.isError || status.isError ? (
        <FormMessage kind="error">Couldn't update the manual login. Try again.</FormMessage>
      ) : null}
      {canStart ? (
        <div>
          <Button
            look="secondary"
            disabled={starting.isLoading}
            onClick={() => void start(supplierId)}
          >
            {attempt ? "Manual login again" : "Manual login"}
          </Button>
        </div>
      ) : null}
      {attempt && OPEN_STATES.has(attempt.state) && attempt.state !== "ready" ? (
        <div>
          <Button
            look="text"
            disabled={cancelling.isLoading}
            onClick={() => void cancel(supplierId)}
          >
            Cancel manual login
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Credentials (write-only), the Login button, the session's age and the pause/retry control. */
export function LoginTab({ supplier }: { supplier: Supplier }) {
  const creds = useCredentialsQuery(supplier.id);
  const [saveCredentials, saving] = useSetCredentialsMutation();
  const [startLogin, starting] = useStartLoginMutation();
  const [retry, retrying] = useRetrySupplierMutation();
  const { register, handleSubmit, reset, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    values: { username: creds.data?.username ?? "", password: "" },
  });

  const submit = handleSubmit(async (values) => {
    try {
      await saveCredentials({ id: supplier.id, ...values }).unwrap();
      reset({ username: values.username, password: "" });
    } catch {
      // saving.isError drives the message
    }
  });

  return (
    <div className="grid gap-gap md:grid-cols-2">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <h2 className="text-section font-semibold">Credentials</h2>
        {creds.isError ? (
          <BlockState kind="error" message="Couldn't load the saved username." onRetry={() => void creds.refetch()} />
        ) : null}
        <TextField label="Username" autoComplete="off" error={errors.username?.message} {...register("username")} />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password")}
        />
        {creds.data?.has_password ? <p className="text-small text-muted">Password saved.</p> : null}
        {saving.isError ? <FormMessage kind="error">Couldn't save the credentials. Try again.</FormMessage> : null}
        <div>
          <Button type="submit" disabled={saving.isLoading}>Save credentials</Button>
        </div>
      </form>

      <div className="flex flex-col gap-4">
        <h2 className="text-section font-semibold">Login</h2>
        <p className="text-body text-muted">
          Login codes: {supplier.two_fa_methods.map((m) => METHOD_NAMES[m]).join(", ") || "none"}.
        </p>
        <p className="text-body">
          Session age: {supplier.session_age_s === null ? "none" : sessionAge(supplier.session_age_s)}
        </p>
        {supplier.paused ? (
          <p role="alert" className="text-body text-negative">
            {supplier.pause_reason ? `Paused: ${supplier.pause_reason}` : "Paused"}
          </p>
        ) : null}
        {starting.isError || retrying.isError ? (
          <FormMessage kind="error">Couldn't start that. Try again.</FormMessage>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void startLogin(supplier.id)} disabled={starting.isLoading}>Log in</Button>
          {supplier.paused ? (
            <Button look="secondary" onClick={() => void retry(supplier.id)} disabled={retrying.isLoading}>
              Retry login
            </Button>
          ) : null}
        </div>
        <ManualLoginControl supplierId={supplier.id} />
      </div>
    </div>
  );
}
