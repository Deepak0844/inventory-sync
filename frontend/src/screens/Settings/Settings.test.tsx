import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { Settings as SettingsData } from "../../api/types";
import { API } from "../../features/suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Settings from "./index";

const data: SettingsData = {
  shopify: { shop_domain: "dev-store.myshopify.com", client_id: "abc123", has_client_secret: true },
  mailbox: { host: "imap.fastmail.com", user: "codes@northline.store", has_password: false },
  kill_switch: { percent: 0.3, max_flips: 20 },
  sold_out_window_h: 6,
  order_poll_min: 15,
};

const serve = () => server.use(http.get(`${API}/settings`, () => HttpResponse.json(data)));

it("shows the saved values and never a secret", async () => {
  serve();
  renderApp(<Settings />);
  expect(await screen.findByDisplayValue("dev-store.myshopify.com")).toBeInTheDocument();
  expect(screen.getByLabelText("Client secret")).toHaveValue("");
  expect(screen.getByText("Client secret saved.")).toBeInTheDocument();
  expect(screen.getByLabelText("Mailbox password")).toHaveValue("");
  expect(screen.queryByText("Mailbox password saved.")).not.toBeInTheDocument();
});

it("shows the kill switch as a percent", async () => {
  serve();
  renderApp(<Settings />);
  expect(await screen.findByLabelText("Hold changes when this share of Listings sell out (%)")).toHaveValue(30);
});

it("saves without secrets when none were typed, converting the percent back", async () => {
  serve();
  let body: Record<string, unknown> = {};
  server.use(
    http.put(`${API}/settings`, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(data);
    }),
  );
  renderApp(<Settings />);
  await screen.findByDisplayValue("dev-store.myshopify.com");
  await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(body.kill_switch).toEqual({ percent: 0.3, max_flips: 20 }));
  expect(body).not.toHaveProperty("client_secret");
  expect(body).not.toHaveProperty("mailbox_password");
  expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
});

it("sends a secret only when one is typed", async () => {
  serve();
  let body: Record<string, unknown> = {};
  server.use(
    http.put(`${API}/settings`, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(data);
    }),
  );
  renderApp(<Settings />);
  await screen.findByDisplayValue("dev-store.myshopify.com");
  await userEvent.type(screen.getByLabelText("Client secret"), "shpss_new");
  await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(body.client_secret).toBe("shpss_new"));
});

it("rejects a share outside 1 to 100 percent", async () => {
  serve();
  renderApp(<Settings />);
  const share = await screen.findByLabelText("Hold changes when this share of Listings sell out (%)");
  await userEvent.clear(share);
  await userEvent.type(share, "150");
  await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
  expect(await screen.findByText("Enter a number from 1 to 100.")).toBeInTheDocument();
});

it("reports the result of testing the Shopify connection", async () => {
  serve();
  server.use(http.post(`${API}/settings/shopify/test`, () => HttpResponse.json({ ok: false, detail: "Invalid client secret" })));
  renderApp(<Settings />);
  await screen.findByDisplayValue("dev-store.myshopify.com");
  await userEvent.click(screen.getByRole("button", { name: "Test Shopify connection" }));
  expect(await screen.findByText("Connection failed: Invalid client secret")).toBeInTheDocument();
});

it("shows an error inside the page when settings cannot load", async () => {
  server.use(http.get(`${API}/settings`, () => new HttpResponse(null, { status: 500 })));
  renderApp(<Settings />);
  expect(await screen.findByText(/Couldn't load Settings/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});
