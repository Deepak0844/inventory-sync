import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { API, supplier } from "../suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { FlowList } from "./FlowList";
import { sampleFlow } from "./testData";

it("lists each Supplier with its flow status, linked to its builder", async () => {
  server.use(
    http.get(`${API}/suppliers`, () => HttpResponse.json([supplier({ id: 1, name: "Supplier A" }), supplier({ id: 2, name: "Supplier B" })])),
    http.get(`${API}/suppliers/1/flow`, () => HttpResponse.json(sampleFlow())),
    http.get(`${API}/suppliers/2/flow`, () => HttpResponse.json({ detail: "No flow yet" }, { status: 404 })),
  );
  renderApp(<FlowList />);
  expect(await screen.findByRole("link", { name: "Supplier A" })).toHaveAttribute("href", "/flows/1");
  expect(await screen.findByText("10 steps")).toBeInTheDocument();
  expect(await screen.findByText("No flow yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Supplier B" })).toHaveAttribute("href", "/flows/2");
});

it("says so when there are no Suppliers to build a flow for", async () => {
  server.use(http.get(`${API}/suppliers`, () => HttpResponse.json([])));
  renderApp(<FlowList />);
  expect(await screen.findByText(/Add a Supplier first/)).toBeInTheDocument();
});

it("shows an error inside the block with Retry", async () => {
  server.use(http.get(`${API}/suppliers`, () => new HttpResponse(null, { status: 500 })));
  renderApp(<FlowList />);
  expect(await screen.findByText(/Couldn't load Suppliers/)).toBeInTheDocument();
});
