import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { API, supplier } from "../../features/suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Suppliers from "./index";

const serve = () =>
  server.use(
    http.get(`${API}/suppliers`, () =>
      HttpResponse.json([
        supplier({ id: 1, name: "Supplier A" }),
        supplier({ id: 2, name: "Supplier B", health: "needs_code", interval_min: 120, listing_count: 40 }),
      ]),
    ),
  );

it("lists each Supplier with its interval and Listing count, linked to its page", async () => {
  serve();
  renderApp(<Suppliers />);
  const link = await screen.findByRole("link", { name: "Supplier B" });
  expect(link).toHaveAttribute("href", "/suppliers/2");
  const row = link.closest("tr")!;
  expect(within(row).getByText("Every 2 h")).toBeInTheDocument();
  expect(within(row).getByText("40")).toBeInTheDocument();
});

it("pills only the Suppliers that need attention", async () => {
  serve();
  renderApp(<Suppliers />);
  await screen.findByRole("link", { name: "Supplier A" });
  expect(screen.getAllByText("Needs code")).toHaveLength(1);
  expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
});

it("says so when there are no Suppliers", async () => {
  server.use(http.get(`${API}/suppliers`, () => HttpResponse.json([])));
  renderApp(<Suppliers />);
  expect(await screen.findByText(/No Suppliers yet/)).toBeInTheDocument();
});

it("shows an error inside the block with Retry", async () => {
  server.use(http.get(`${API}/suppliers`, () => new HttpResponse(null, { status: 500 })));
  renderApp(<Suppliers />);
  expect(await screen.findByText(/Couldn't load Suppliers/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

it("adds a Supplier from the dialog", async () => {
  serve();
  let body: unknown;
  server.use(
    http.post(`${API}/suppliers`, async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(supplier({ id: 3, name: "Supplier C" }), { status: 201 });
    }),
  );
  renderApp(<Suppliers />);
  await userEvent.click(await screen.findByRole("button", { name: "Add Supplier" }));
  const dialog = screen.getByRole("dialog", { name: "Add Supplier" });
  await userEvent.type(within(dialog).getByLabelText("Name"), "Supplier C");
  await userEvent.type(within(dialog).getByLabelText("Site URL"), "https://c.example");
  await userEvent.clear(within(dialog).getByLabelText("Check every (minutes)"));
  await userEvent.type(within(dialog).getByLabelText("Check every (minutes)"), "240");
  await userEvent.click(within(dialog).getByLabelText("Mailbox code"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Create Supplier" }));
  await waitFor(() =>
    expect(body).toEqual({
      name: "Supplier C",
      site_url: "https://c.example",
      interval_min: 240,
      two_fa_methods: ["ui_code", "email_code"],
    }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("rejects a blank name and a bad URL without calling the API", async () => {
  serve();
  let called = false;
  server.use(http.post(`${API}/suppliers`, () => ((called = true), HttpResponse.json({}))));
  renderApp(<Suppliers />);
  await userEvent.click(await screen.findByRole("button", { name: "Add Supplier" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Site URL"), "not a url");
  await userEvent.click(within(dialog).getByRole("button", { name: "Create Supplier" }));
  expect(await within(dialog).findByText("Enter a name.")).toBeInTheDocument();
  expect(within(dialog).getByText("Enter a full address, like https://supplier.example.")).toBeInTheDocument();
  expect(called).toBe(false);
});
