import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Orders from "./index";

const url = (p: string) => `http://localhost:3000/api${p}`;
const order = {
  order_id: "gid://shopify/Order/1", name: "#1042", created_at: new Date(Date.now() - 4 * 3_600_000).toISOString(),
  reasons: ["stale", "recently_sold_out"],
  variants: [{ sku: "SHOE-BLK-L", reason: "stale" }, { sku: "SHOE-RED-M", reason: "recently_sold_out" }],
};

it("lists flagged orders with a pill for each reason and the affected SKUs", async () => {
  server.use(http.get(url("/orders/flagged"), () => HttpResponse.json([
    order, { ...order, order_id: "2", name: "#1043", reasons: ["lines_truncated"], variants: [] },
  ])));
  renderApp(<Orders />);
  expect(await screen.findByText("#1042")).toBeInTheDocument();
  expect(screen.getByText("Stale")).toBeInTheDocument();
  expect(screen.getByText("Sold out recently")).toBeInTheDocument();
  expect(screen.getByText("Lines truncated")).toBeInTheDocument();
  expect(screen.getByText("SHOE-BLK-L, SHOE-RED-M")).toBeInTheDocument();
  expect(screen.getAllByText("4 h ago")).toHaveLength(2);
  expect(screen.getByText("2 orders")).toBeInTheDocument();
});

it("says the system only flags orders", async () => {
  server.use(http.get(url("/orders/flagged"), () => HttpResponse.json([order])));
  renderApp(<Orders />);
  expect(await screen.findByText(/never cancels orders or contacts customers/)).toBeInTheDocument();
});

it("shows an empty state", async () => {
  server.use(http.get(url("/orders/flagged"), () => HttpResponse.json([])));
  renderApp(<Orders />);
  expect(await screen.findByText("No orders need checking.")).toBeInTheDocument();
});

it("shows an error in the block with Retry", async () => {
  let fail = true;
  server.use(http.get(url("/orders/flagged"), () => (fail ? new HttpResponse(null, { status: 500 }) : HttpResponse.json([]))));
  renderApp(<Orders />);
  expect(await screen.findByText(/Couldn't load orders/)).toBeInTheDocument();
  fail = false;
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No orders need checking.")).toBeInTheDocument();
});
