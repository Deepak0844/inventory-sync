import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { VariantRow } from "../../api/types";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Variants from "./index";

const url = (p: string) => `http://localhost:3000/api${p}`;
// A margin past the hour: the mock builds these after the component's clock was read.
const hoursAgo = (h: number) => new Date(Date.now() - (h + 0.1) * 3_600_000).toISOString();
const reading = (result: "in_stock" | "out_of_stock" | "unknown", n: number) => ({ result, read_at: `2026-11-03T10:${String(n).padStart(2, "0")}:00Z` });

const row = (over: Partial<VariantRow> = {}): VariantRow => ({
  id: 1, shopify_variant_id: "gid://shopify/ProductVariant/1", sku: "SHOE-BLK-L", title: "Black / L",
  state: "available", sold_out_at: null, stale: false, listings: [], readings: [], ...over,
});
const page = (items: VariantRow[], total = items.length, next: string | null = null) => ({ items, total, next_cursor: next });

function serve(make: (p: URLSearchParams) => Record<string, unknown>) {
  const seen: URLSearchParams[] = [];
  server.use(http.get(url("/variants"), ({ request }) => {
    const p = new URL(request.url).searchParams;
    seen.push(p);
    return HttpResponse.json(make(p));
  }));
  return seen;
}

it("shows what is Sold Out and since when, with the reading strip and a Stale mark", async () => {
  serve(() => page([
    row({ id: 1, sku: "SOLD-1", state: "sold_out", sold_out_at: hoursAgo(5),
      readings: [reading("in_stock", 0), reading("out_of_stock", 1), reading("out_of_stock", 2)] }),
    row({ id: 2, sku: "OK-2", state: "available" }),
    row({ id: 3, sku: "OLD-3", state: "available", stale: true, readings: [reading("unknown", 0)] }),
  ], 3));
  renderApp(<Variants />);
  const soldRow = (await screen.findByText("SOLD-1")).closest("tr") as HTMLElement;
  expect(within(soldRow).getByText("Sold out")).toBeInTheDocument();
  expect(within(soldRow).getByText("5 h ago")).toBeInTheDocument();
  expect(within(soldRow).getAllByTestId("tick")).toHaveLength(3);
  const okRow = screen.getByText("OK-2").closest("tr") as HTMLElement;
  expect(within(okRow).queryByText("Sold out")).not.toBeInTheDocument();
  expect(within(okRow).queryByText("Stale")).not.toBeInTheDocument();
  expect(within(screen.getByText("OLD-3").closest("tr") as HTMLElement).getByText("Stale")).toBeInTheDocument();
  expect(screen.getByText("3 variants")).toBeInTheDocument();
});

it("filters by state and by Stale", async () => {
  const seen = serve(() => page([row()]));
  renderApp(<Variants />);
  await screen.findByText("SHOE-BLK-L");
  await userEvent.selectOptions(screen.getByLabelText("State"), "Sold out");
  await waitFor(() => expect(seen.at(-1)?.get("state")).toBe("sold_out"));
  await userEvent.click(screen.getByLabelText("Stale only"));
  await waitFor(() => expect(seen.at(-1)?.get("stale")).toBe("true"));
});

it("starts from the search in the address, as the top bar search sends it", async () => {
  const seen = serve(() => page([row()]));
  renderApp(<Variants />, "/variants?q=shoe");
  await screen.findByText("SHOE-BLK-L");
  expect(seen[0].get("q")).toBe("shoe");
  expect(screen.getByLabelText("Search")).toHaveValue("shoe");
});

it("loads more at the end and keeps earlier rows", async () => {
  serve((p) => (p.get("cursor") === "c2"
    ? page([row({ id: 2, sku: "SECOND" })], 2)
    : page([row({ id: 1, sku: "FIRST" })], 2, "c2")));
  renderApp(<Variants />);
  await screen.findByText("FIRST");
  await userEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("SECOND")).toBeInTheDocument();
  expect(screen.getByText("FIRST")).toBeInTheDocument();
});

it("shows an error in the block with Retry, and an empty state", async () => {
  let fail = true;
  server.use(http.get(url("/variants"), () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(page([])))));
  renderApp(<Variants />);
  expect(await screen.findByText(/Couldn't load variants/)).toBeInTheDocument();
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText(/No variants/)).toBeInTheDocument();
});
