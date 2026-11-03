import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { Overview as OverviewData } from "../../api/types";
import { API } from "../../features/suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Overview from "./index";

const change = (i: number) => ({
  at: new Date(Date.now() - i * 3_600_000).toISOString(),
  sku: `SKU-${i}`,
  from_state: "available" as const,
  to_state: "sold_out" as const,
  reason: "all_out_of_stock",
});

const data: OverviewData = {
  updated_at: new Date().toISOString(),
  kpis: { sold_out: 14, in_stock: 1186, stale: 3, pending: 2 },
  sold_out_by_day: [
    { date: "2026-11-01", count: 5 },
    { date: "2026-11-02", count: 9 },
    { date: "2026-11-03", count: 14 },
  ],
  suppliers: [
    { id: 1, name: "Supplier A", health: "healthy", last_success_at: new Date().toISOString() },
    { id: 2, name: "Supplier B", health: "needs_code", last_success_at: null },
  ],
  recent_changes: Array.from({ length: 8 }, (_, i) => change(i + 1)),
};

const serve = (body: OverviewData = data) =>
  server.use(http.get(`${API}/overview`, () => HttpResponse.json(body)));

it("opens with the finding, then the four counts in one card", async () => {
  serve();
  renderApp(<Overview />);
  expect(await screen.findByText("14 variants are sold out. Supplier B needs a code.")).toBeInTheDocument();
  const kpis = screen.getByRole("group", { name: "Stock counts" });
  expect(within(kpis).getByText("1,186")).toBeInTheDocument();
  for (const label of ["Sold Out", "In Stock", "Stale", "Pending"]) {
    expect(within(kpis).getByText(label)).toBeInTheDocument();
  }
});

it("draws the sold out line once, with a text alternative", async () => {
  serve();
  renderApp(<Overview />);
  const chart = await screen.findByRole("img", { name: /Sold Out variants per day/ });
  expect(chart.querySelectorAll("path")).toHaveLength(1);
  expect(chart.querySelectorAll("line")).toHaveLength(4);
});

it("marks the Supplier that needs attention and leaves the healthy one bare", async () => {
  serve();
  renderApp(<Overview />);
  await screen.findByText(/14 variants are sold out/);
  const health = screen.getByRole("heading", { name: "Supplier health" }).closest("section")!;
  expect(within(health).getByText("Needs code")).toBeInTheDocument();
  expect(within(health).queryByText("Healthy")).not.toBeInTheDocument();
  expect(within(health).getByRole("link", { name: "View all" })).toHaveAttribute("href", "/suppliers");
});

it("caps recent changes at five rows with a link to the rest", async () => {
  serve();
  renderApp(<Overview />);
  await screen.findByText(/14 variants are sold out/);
  const changes = screen.getByRole("heading", { name: "Recent changes" }).closest("section")!;
  expect(within(changes).getAllByRole("listitem")).toHaveLength(5);
  expect(within(changes).getByRole("link", { name: "View all" })).toHaveAttribute("href", "/variants");
});

it("shows a zero as 0 and says so in the sentence", async () => {
  serve({ ...data, kpis: { sold_out: 0, in_stock: 0, stale: 0, pending: 0 }, suppliers: [], recent_changes: [] });
  renderApp(<Overview />);
  expect(await screen.findByText("No variants are sold out.")).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "Stock counts" })).getAllByText("0")).toHaveLength(4);
  expect(screen.getByText("No changes yet.")).toBeInTheDocument();
});

it("keeps the layout while loading, with grey bars instead of values", () => {
  server.use(http.get(`${API}/overview`, () => new Promise(() => {})));
  renderApp(<Overview />);
  expect(screen.getAllByTestId("block-loading").length).toBeGreaterThan(0);
});

it("fails inside each block and recovers on Retry", async () => {
  let calls = 0;
  server.use(
    http.get(`${API}/overview`, () => (++calls === 1 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(data))),
  );
  renderApp(<Overview />);
  const retries = await screen.findAllByRole("button", { name: "Retry" });
  expect(screen.getAllByText(/Couldn't load/).length).toBeGreaterThan(1);
  await userEvent.click(retries[0]);
  await waitFor(() => expect(screen.getByText(/14 variants are sold out/)).toBeInTheDocument());
});
