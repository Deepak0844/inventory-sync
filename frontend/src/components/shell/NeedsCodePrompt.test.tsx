import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { NeedsCodePrompt } from "./NeedsCodePrompt";

const url = (p: string) => `http://localhost:3000/api${p}`;
const soon = () => new Date(Date.now() + 5 * 60_000).toISOString();

it("shows nothing while no Supplier is waiting", async () => {
  server.use(http.get(url("/login-code/pending"), () => HttpResponse.json([])));
  const { container } = renderApp(<NeedsCodePrompt />);
  await waitFor(() => expect(container).toBeEmptyDOMElement());
});

it("names the waiting Supplier and shows a countdown", async () => {
  server.use(
    http.get(url("/login-code/pending"), () =>
      HttpResponse.json([{ supplier_id: 2, supplier_name: "Supplier B", expires_at: soon() }]),
    ),
  );
  renderApp(<NeedsCodePrompt />);
  expect(await screen.findByText("Supplier B needs a code")).toBeInTheDocument();
  expect(screen.getByText(/\d+:\d\d left/)).toBeInTheDocument();
});

it("submits the pasted code for that Supplier", async () => {
  let body: unknown;
  server.use(
    http.get(url("/login-code/pending"), () =>
      HttpResponse.json([{ supplier_id: 2, supplier_name: "Supplier B", expires_at: soon() }]),
    ),
    http.post(url("/suppliers/2/login-code"), async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 202 });
    }),
  );
  renderApp(<NeedsCodePrompt />);
  await userEvent.type(await screen.findByLabelText("Login Code"), "123456");
  await userEvent.click(screen.getByRole("button", { name: "Submit" }));
  await waitFor(() => expect(body).toEqual({ code: "123456" }));
});

it("does not submit a blank code", async () => {
  const posted = vi.fn();
  server.use(
    http.get(url("/login-code/pending"), () =>
      HttpResponse.json([{ supplier_id: 2, supplier_name: "Supplier B", expires_at: soon() }]),
    ),
    http.post(url("/suppliers/2/login-code"), () => {
      posted();
      return new HttpResponse(null, { status: 202 });
    }),
  );
  renderApp(<NeedsCodePrompt />);
  await userEvent.click(await screen.findByRole("button", { name: "Submit" }));
  expect(posted).not.toHaveBeenCalled();
});
