import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useTestShopifyMutation, useUpdateSettingsMutation } from "../../api/api";
import type { Settings, SettingsUpdate } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { TextField } from "../../components/ui/TextField";
import { FormMessage } from "../suppliers/fields";
import { WHOLE_NUMBER_MESSAGE } from "../suppliers/format";
import { fractionToPercent, percentToFraction } from "./killSwitch";

const whole = z.number({ invalid_type_error: WHOLE_NUMBER_MESSAGE }).int(WHOLE_NUMBER_MESSAGE).min(1, WHOLE_NUMBER_MESSAGE);
const schema = z.object({
  shop_domain: z.string().trim().min(1, "Enter the shop domain."),
  client_id: z.string().trim().min(1, "Enter the client ID."),
  client_secret: z.string(),
  mailbox_host: z.string().trim(),
  mailbox_user: z.string().trim(),
  mailbox_password: z.string(),
  percent: z.number({ invalid_type_error: "Enter a number from 1 to 100." }).min(1, "Enter a number from 1 to 100.").max(100, "Enter a number from 1 to 100."),
  max_flips: whole,
  sold_out_window_h: whole,
  order_poll_min: whole,
});
type Values = z.infer<typeof schema>;

const toValues = (s: Settings): Values => ({
  shop_domain: s.shopify.shop_domain,
  client_id: s.shopify.client_id,
  client_secret: "",
  mailbox_host: s.mailbox.host,
  mailbox_user: s.mailbox.user,
  mailbox_password: "",
  percent: fractionToPercent(s.kill_switch.percent),
  max_flips: s.kill_switch.max_flips,
  sold_out_window_h: s.sold_out_window_h,
  order_poll_min: s.order_poll_min,
});

/** Secrets are write-only: they are sent only when the person typed a new one. */
const toUpdate = (v: Values): SettingsUpdate => ({
  shopify: { shop_domain: v.shop_domain, client_id: v.client_id, has_client_secret: false },
  mailbox: { host: v.mailbox_host, user: v.mailbox_user, has_password: false },
  kill_switch: { percent: percentToFraction(v.percent), max_flips: v.max_flips },
  sold_out_window_h: v.sold_out_window_h,
  order_poll_min: v.order_poll_min,
  ...(v.client_secret ? { client_secret: v.client_secret } : {}),
  ...(v.mailbox_password ? { mailbox_password: v.mailbox_password } : {}),
});

/** The system's rules: Shopify connection, mailbox, kill switch and order flagging. */
export function SettingsForm({ settings }: { settings: Settings }) {
  const [save, saving] = useUpdateSettingsMutation();
  const [test, testing] = useTestShopifyMutation();
  const { register, handleSubmit, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(settings),
  });
  const submit = handleSubmit(async (values) => {
    try {
      await save(toUpdate(values)).unwrap();
    } catch {
      // saving.isError drives the message
    }
  });
  const result = testing.data;

  return (
    <form onSubmit={submit} noValidate className="flex max-w-2xl flex-col gap-gap">
      <Card title="Shopify">
        <div className="flex flex-col gap-4">
          <TextField label="Shop domain" error={errors.shop_domain?.message} {...register("shop_domain")} />
          <TextField label="Client ID" error={errors.client_id?.message} {...register("client_id")} />
          <TextField
            label="Client secret"
            type="password"
            autoComplete="new-password"
            placeholder={settings.shopify.has_client_secret ? "Leave blank to keep the saved secret" : ""}
            {...register("client_secret")}
          />
          {settings.shopify.has_client_secret ? (
            <p className="-mt-3 text-small text-muted">Client secret saved.</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button look="secondary" onClick={() => void test()} disabled={testing.isLoading}>Test Shopify connection</Button>
            <span className="text-small text-muted">Tests the saved credentials. It never changes inventory.</span>
          </div>
          {result ? (
            <FormMessage kind={result.ok ? "ok" : "error"}>
              {result.ok ? `Connected. ${result.detail}`.trim() : `Connection failed: ${result.detail}`}
            </FormMessage>
          ) : null}
          {testing.isError ? <FormMessage kind="error">Couldn't run the test. Try again.</FormMessage> : null}
        </div>
      </Card>

      <Card title="Mailbox for Login Codes">
        <div className="flex flex-col gap-4">
          <TextField label="Mailbox host" {...register("mailbox_host")} />
          <TextField label="Mailbox user" {...register("mailbox_user")} />
          <TextField
            label="Mailbox password"
            type="password"
            autoComplete="new-password"
            placeholder={settings.mailbox.has_password ? "Leave blank to keep the saved password" : ""}
            {...register("mailbox_password")}
          />
          {settings.mailbox.has_password ? (
            <p className="-mt-3 text-small text-muted">Mailbox password saved.</p>
          ) : null}
        </div>
      </Card>

      <Card title="Safety and orders">
        <div className="flex flex-col gap-4">
          <TextField
            label="Hold changes when this share of Listings sell out (%)"
            type="number"
            error={errors.percent?.message}
            {...register("percent", { valueAsNumber: true })}
          />
          <TextField
            label="...or more than this many Listings"
            type="number"
            error={errors.max_flips?.message}
            {...register("max_flips", { valueAsNumber: true })}
          />
          <TextField
            label="Treat a Variant as recently sold out for (hours)"
            type="number"
            error={errors.sold_out_window_h?.message}
            {...register("sold_out_window_h", { valueAsNumber: true })}
          />
          <TextField
            label="Check orders every (minutes)"
            type="number"
            error={errors.order_poll_min?.message}
            {...register("order_poll_min", { valueAsNumber: true })}
          />
        </div>
      </Card>

      {saving.isError ? <FormMessage kind="error">Couldn't save the settings. Try again.</FormMessage> : null}
      {saving.isSuccess && !saving.isLoading ? <FormMessage kind="ok">Settings saved.</FormMessage> : null}
      <div>
        <Button type="submit" disabled={saving.isLoading}>Save settings</Button>
      </div>
    </form>
  );
}
