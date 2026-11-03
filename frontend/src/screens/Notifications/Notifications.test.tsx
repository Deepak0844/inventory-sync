import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { AppNotification } from "../../api/types";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Notifications from "./index";

const url = (p: string) => `http://localhost:3000/api${p}`;
const n = (over: Partial<AppNotification>): AppNotification => ({
  id: 1, kind: "flow_failure", supplier_id: 2, supplier_name: "Supplier B",
  message: "The stock element was not found on 12 Listings.",
  created_at: new Date(Date.now() - 30.5 * 60_000).toISOString(), resolved_at: null, screenshot_url: null, ...over,
});

it("asks only for unresolved notifications", async () => {
  let resolved: string | null = null;
  server.use(http.get(url("/notifications"), ({ request }) => {
    resolved = new URL(request.url).searchParams.get("resolved");
    return HttpResponse.json([]);
  }));
  renderApp(<Notifications />);
  await screen.findByText("Nothing needs fixing.");
  expect(resolved).toBe("false");
});

it("shows the kind in plain words with the Supplier, message and age", async () => {
  server.use(http.get(url("/notifications"), () => HttpResponse.json([
    n({ id: 1 }),
    n({ id: 2, kind: "shopify_error", supplier_id: null, supplier_name: null, message: "Shopify returned 503." }),
  ])));
  renderApp(<Notifications />);
  expect(await screen.findByText("Flow failure")).toBeInTheDocument();
  expect(screen.getByText("Supplier B")).toBeInTheDocument();
  expect(screen.getByText("The stock element was not found on 12 Listings.")).toBeInTheDocument();
  expect(screen.getByText("Shopify error")).toBeInTheDocument();
  expect(screen.getAllByText("30 min ago")).toHaveLength(2);
});

it("links to the screenshot only when there is one", async () => {
  server.use(http.get(url("/notifications"), () => HttpResponse.json([
    n({ id: 1, screenshot_url: "/screenshots/1.png" }), n({ id: 2 }),
  ])));
  renderApp(<Notifications />);
  const link = await screen.findByRole("link", { name: "View screenshot" });
  expect(link).toHaveAttribute("href", "/screenshots/1.png");
  expect(screen.getAllByRole("link", { name: "View screenshot" })).toHaveLength(1);
});

it("resolves a notification and refetches", async () => {
  let calls = 0;
  let resolvedId = 0;
  server.use(
    http.get(url("/notifications"), () => HttpResponse.json(calls++ === 0 ? [n({ id: 9 })] : [])),
    http.post(url("/notifications/9/resolve"), () => { resolvedId = 9; return new HttpResponse(null, { status: 204 }); }),
  );
  renderApp(<Notifications />);
  await userEvent.click(await screen.findByRole("button", { name: "Resolve" }));
  await waitFor(() => expect(resolvedId).toBe(9));
  expect(await screen.findByText("Nothing needs fixing.")).toBeInTheDocument();
});

it("shows an error in the block with Retry", async () => {
  let fail = true;
  server.use(http.get(url("/notifications"), () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json([]))));
  renderApp(<Notifications />);
  expect(await screen.findByText(/Couldn't load notifications/)).toBeInTheDocument();
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Nothing needs fixing.")).toBeInTheDocument();
});
