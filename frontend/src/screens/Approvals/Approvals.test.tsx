import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { Approval } from "../../api/types";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Approvals from "./index";

const url = (p: string) => `http://localhost:3000/api${p}`;
const batch: Approval = {
  id: 5, supplier_id: 2, supplier_name: "Supplier B", created_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
  changes: [
    { variant_id: 1, sku: "SHOE-BLK-L", from_state: "available", to_state: "sold_out" },
    { variant_id: 2, sku: "SHOE-RED-M", from_state: "available", to_state: "sold_out" },
  ],
};

it("says nothing is waiting when there are no batches", async () => {
  server.use(http.get(url("/approvals"), () => HttpResponse.json([])));
  renderApp(<Approvals />);
  expect(await screen.findByText("No changes are waiting for you.")).toBeInTheDocument();
});

it("lists each batch with its Supplier, age and Variant changes", async () => {
  server.use(http.get(url("/approvals"), () => HttpResponse.json([batch])));
  renderApp(<Approvals />);
  expect(await screen.findByText("Supplier B")).toBeInTheDocument();
  expect(screen.getByText("2 h ago")).toBeInTheDocument();
  expect(screen.getByText("SHOE-BLK-L")).toBeInTheDocument();
  expect(screen.getAllByText("In stock → Sold out")).toHaveLength(2);
});

it("asks for confirmation before applying, then approves", async () => {
  let approved = 0;
  let calls = 0;
  server.use(
    http.get(url("/approvals"), () => HttpResponse.json(calls++ === 0 ? [batch] : [])),
    http.post(url("/approvals/5/approve"), () => {
      approved++;
      return new HttpResponse(null, { status: 202 });
    }),
  );
  renderApp(<Approvals />);
  await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
  expect(approved).toBe(0);
  expect(screen.getByText("Apply 2 changes to Shopify?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Yes, apply" }));
  await waitFor(() => expect(approved).toBe(1));
  expect(await screen.findByText("No changes are waiting for you.")).toBeInTheDocument();
});

it("can back out of the confirmation without calling the API", async () => {
  let approved = 0;
  server.use(
    http.get(url("/approvals"), () => HttpResponse.json([batch])),
    http.post(url("/approvals/5/approve"), () => { approved++; return new HttpResponse(null, { status: 202 }); }),
  );
  renderApp(<Approvals />);
  await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByText("Apply 2 changes to Shopify?")).not.toBeInTheDocument();
  expect(approved).toBe(0);
});

it("rejects a batch and refetches", async () => {
  let rejected = 0;
  let calls = 0;
  server.use(
    http.get(url("/approvals"), () => HttpResponse.json(calls++ === 0 ? [batch] : [])),
    http.post(url("/approvals/5/reject"), () => { rejected++; return new HttpResponse(null, { status: 204 }); }),
  );
  renderApp(<Approvals />);
  await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
  await waitFor(() => expect(rejected).toBe(1));
  expect(await screen.findByText("No changes are waiting for you.")).toBeInTheDocument();
});

it("shows an error inside the block and says when approving failed", async () => {
  server.use(
    http.get(url("/approvals"), () => HttpResponse.json([batch])),
    http.post(url("/approvals/5/approve"), () => new HttpResponse(null, { status: 500 })),
  );
  renderApp(<Approvals />);
  await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, apply" }));
  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(/Couldn't approve this batch/)).toBeInTheDocument();
});
