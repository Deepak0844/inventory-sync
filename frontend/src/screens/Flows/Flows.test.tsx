import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { installBrowserShims } from "../../features/flowBuilder/testSupport";
import { sampleFlow } from "../../features/flowBuilder/testData";
import { API, supplier } from "../../features/suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import Flows from "./index";

beforeEach(() => installBrowserShims());

it("lists the Suppliers at the top of the section", async () => {
  server.use(
    http.get(`${API}/suppliers`, () => HttpResponse.json([supplier()])),
    http.get(`${API}/suppliers/1/flow`, () => HttpResponse.json(sampleFlow())),
  );
  renderApp(<Flows />, "/");
  expect(await screen.findByRole("link", { name: "Supplier A" })).toHaveAttribute("href", "/flows/1");
});

it("opens the builder for the Supplier in the address", async () => {
  server.use(
    http.get(`${API}/suppliers/1`, () => HttpResponse.json(supplier())),
    http.get(`${API}/suppliers/1/flow`, () => HttpResponse.json(sampleFlow())),
  );
  renderApp(<Flows />, "/1");
  expect(await screen.findByText("https://supplier-a.example/login")).toBeInTheDocument();
});

it("says so when the address is not a Supplier", async () => {
  renderApp(<Flows />, "/abc");
  expect(await screen.findByText(/isn't a Supplier/)).toBeInTheDocument();
});
