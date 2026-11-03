import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { Listing, Supplier, VariantRow } from "../../api/types";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Listings from "./index";

const url = (p: string) => `http://localhost:3000/api${p}`;
// A margin past the hour: the mock builds these after the component's clock was read.
const hoursAgo = (h: number) => new Date(Date.now() - (h + 0.1) * 3_600_000).toISOString();

const listing = (over: Partial<Listing> = {}): Listing => ({
  id: 1, supplier_id: 1, url: "https://a.test/p/1", selection_hint: null, status: "in_stock",
  quantity: 7, removed: false, last_success_at: hoursAgo(3), ...over,
});
const supplier = (id: number, name: string) => ({ id, name } as Supplier);
const page = (items: Listing[], total = items.length, next: string | null = null) => ({ items, total, next_cursor: next });

function serve(listings: (p: URLSearchParams) => Record<string, unknown>) {
  const seen: URLSearchParams[] = [];
  server.use(
    http.get(url("/suppliers"), () => HttpResponse.json([supplier(1, "Supplier A"), supplier(2, "Supplier B")])),
    http.get(url("/listings"), ({ request }) => {
      const p = new URL(request.url).searchParams;
      seen.push(p);
      return HttpResponse.json(listings(p));
    }),
    http.get(url("/variants"), () => HttpResponse.json(page([] as unknown as Listing[]))),
  );
  return seen;
}

it("shows Listings with a total and one status mark per row", async () => {
  serve(() => page([
    listing({ id: 1, status: "out_of_stock", quantity: null }),
    listing({ id: 2, url: "https://a.test/p/2", removed: true, status: "out_of_stock" }),
    listing({ id: 3, url: "https://a.test/p/3", status: "unknown", last_success_at: null }),
  ], 1203));
  renderApp(<Listings />);
  expect(await screen.findByText("https://a.test/p/1")).toBeInTheDocument();
  expect(screen.getByText("1,203 listings")).toBeInTheDocument();
  expect(screen.getByText("Out of stock")).toBeInTheDocument();
  expect(screen.getByText("Listing removed")).toBeInTheDocument();
  expect(screen.getByText("Unknown")).toBeInTheDocument();
  expect(screen.getAllByText("3 h ago")).toHaveLength(2);
});

it("filters by Supplier", async () => {
  const seen = serve(() => page([listing()]));
  renderApp(<Listings />);
  await screen.findByText("https://a.test/p/1");
  await userEvent.selectOptions(await screen.findByLabelText("Supplier"), "Supplier B");
  await waitFor(() => expect(seen.at(-1)?.get("supplier_id")).toBe("2"));
});

it("searches by text", async () => {
  const seen = serve(() => page([listing()]));
  renderApp(<Listings />);
  await screen.findByText("https://a.test/p/1");
  await userEvent.type(screen.getByLabelText("Search"), "shoe");
  await waitFor(() => expect(seen.at(-1)?.get("q")).toBe("shoe"));
});

it("loads the next page and keeps the rows already shown", async () => {
  const seen = serve((p) =>
    p.get("cursor") === "c2"
      ? page([listing({ id: 2, url: "https://a.test/p/2" })], 2)
      : page([listing({ id: 1 })], 2, "c2"),
  );
  renderApp(<Listings />);
  await screen.findByText("https://a.test/p/1");
  await userEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("https://a.test/p/2")).toBeInTheDocument();
  expect(screen.getByText("https://a.test/p/1")).toBeInTheDocument();
  expect(seen.at(-1)?.get("cursor")).toBe("c2");
});

it("shows an error inside the block and retries", async () => {
  let fail = true;
  serve(() => page([listing()]));
  server.use(http.get(url("/listings"), () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(page([listing()])))));
  renderApp(<Listings />);
  expect(await screen.findByText(/Couldn't load listings/)).toBeInTheDocument();
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("https://a.test/p/1")).toBeInTheDocument();
});

it("shows an empty state that keeps the header", async () => {
  serve(() => page([]));
  renderApp(<Listings />);
  expect(await screen.findByText(/No listings/)).toBeInTheDocument();
  expect(screen.getByText("Status")).toBeInTheDocument();
});

describe("CSV import", () => {
  it("posts the file and reports created, updated and errors by row", async () => {
    serve(() => page([listing()]));
    let contentType: string | null = null;
    // The body is not read: jsdom's File stream hangs under msw. The content type shows it went as multipart.
    server.use(http.post(url("/listings/import"), ({ request }) => {
      contentType = request.headers.get("content-type");
      return HttpResponse.json({ created: 2, updated: 1, errors: [{ row: 4, message: "Unknown SKU" }] });
    }));
    renderApp(<Listings />);
    await screen.findByText("https://a.test/p/1");
    await userEvent.click(screen.getByRole("button", { name: "Import CSV" }));
    const dialog = screen.getByRole("dialog", { name: "Import listings" });
    const file = new File(["sku,supplier,url\nA,Supplier A,https://a.test"], "listings.csv", { type: "text/csv" });
    await userEvent.upload(within(dialog).getByLabelText("CSV file"), file);
    await userEvent.click(within(dialog).getByRole("button", { name: "Import" }));
    expect(await within(dialog).findByText("2 created, 1 updated")).toBeInTheDocument();
    expect(within(dialog).getByText("Row 4: Unknown SKU")).toBeInTheDocument();
    expect(contentType).toMatch(/^multipart\/form-data/);
  });

  it("asks for a file before importing", async () => {
    serve(() => page([listing()]));
    renderApp(<Listings />);
    await screen.findByText("https://a.test/p/1");
    await userEvent.click(screen.getByRole("button", { name: "Import CSV" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Import" }));
    expect(screen.getByText("Choose a CSV file first.")).toBeInTheDocument();
  });
});

describe("mapping editor", () => {
  const variant: VariantRow = {
    id: 7, shopify_variant_id: "gid://shopify/ProductVariant/7", sku: "SHOE-BLK-L", title: "Black / L",
    state: "available", sold_out_at: null, stale: false, readings: [],
    listings: [{ listing_id: 1, supplier_id: 1, priority: 1 }, { listing_id: 2, supplier_id: 1, priority: 2 }],
  };

  it("reorders the Listings of a Variant and saves the new priorities", async () => {
    serve(() => page([listing({ id: 1 }), listing({ id: 2, url: "https://a.test/p/2" })]));
    let put: unknown;
    server.use(
      http.get(url("/variants"), () => HttpResponse.json({ items: [variant], total: 1, next_cursor: null })),
      http.get(url("/variants/7/mappings"), () => HttpResponse.json([
        { listing_id: 1, priority: 1 }, { listing_id: 2, priority: 2 },
      ])),
      http.put(url("/variants/7/mappings"), async ({ request }) => {
        put = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp(<Listings />);
    await userEvent.type(await screen.findByLabelText("Find a variant"), "SHOE");
    await userEvent.click(await screen.findByRole("button", { name: "Edit mapping for SHOE-BLK-L" }));
    const editor = await screen.findByRole("region", { name: "Mapping for SHOE-BLK-L" });
    expect(await within(editor).findByText("https://a.test/p/2")).toBeInTheDocument();
    await userEvent.click(within(editor).getByRole("button", { name: "Move https://a.test/p/1 down" }));
    await userEvent.click(within(editor).getByRole("button", { name: "Save mapping" }));
    await waitFor(() => expect(put).toEqual([{ listing_id: 2, priority: 1 }, { listing_id: 1, priority: 2 }]));
  });
});
