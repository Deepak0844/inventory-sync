import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router-dom";

import { API, supplier } from "../../features/suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import SupplierDetail from "./index";

const open = (over = {}) => {
  server.use(
    http.get(`${API}/suppliers/1`, () => HttpResponse.json(supplier(over))),
    http.get(`${API}/suppliers/1/credentials`, () => HttpResponse.json({ username: "shop-owner", has_password: true })),
    http.get(`${API}/suppliers/1/flow`, () => HttpResponse.json({ supplier: "supplier-a", version: 1 })),
    http.get(`${API}/suppliers/1/manual-login`, () =>
      HttpResponse.json({ enabled: false, session: null }),
    ),
    http.get(`${API}/suppliers/1/runs`, () =>
      HttpResponse.json({
        items: [{ id: 9, kind: "check", state: "done", started_at: new Date().toISOString(), finished_at: null, summary: "120 listings read" }],
      }),
    ),
    http.get(`${API}/listings`, () =>
      HttpResponse.json({
        items: [{ id: 5, supplier_id: 1, url: "https://supplier-a.example/p/5", selection_hint: "Black / L", status: "out_of_stock", quantity: null, removed: false, last_success_at: null }],
        total: 1,
        next_cursor: null,
      }),
    ),
  );
  return renderApp(
    <Routes><Route path="/suppliers/:id" element={<SupplierDetail />} /></Routes>,
    "/suppliers/1",
  );
};

it("names the Supplier and opens on its Listings", async () => {
  open();
  expect(await screen.findByRole("heading", { name: "Supplier A" })).toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
    "Listings", "Flow", "Login and 2FA", "Runs", "Settings",
  ]);
  expect(await screen.findByText("Black / L")).toBeInTheDocument();
});

it("shows a missing Supplier as an error inside the page", async () => {
  server.use(http.get(`${API}/suppliers/1`, () => new HttpResponse(null, { status: 404 })));
  renderApp(<Routes><Route path="/suppliers/:id" element={<SupplierDetail />} /></Routes>, "/suppliers/1");
  expect(await screen.findByText(/Couldn't load this Supplier/)).toBeInTheDocument();
});

describe("Flow tab", () => {
  const goToFlow = async () => {
    open();
    await userEvent.click(await screen.findByRole("tab", { name: "Flow" }));
    return screen.findByLabelText("Flow definition (JSON)");
  };

  it("loads the saved flow into the editor", async () => {
    const editor = await goToFlow();
    await waitFor(() => expect((editor as HTMLTextAreaElement).value).toContain('"supplier": "supplier-a"'));
  });

  it("does not send JSON that does not parse", async () => {
    let called = false;
    server.use(http.put(`${API}/suppliers/1/flow`, () => ((called = true), HttpResponse.json({}))));
    const editor = await goToFlow();
    await userEvent.clear(editor);
    await userEvent.type(editor, "{{oops");
    await userEvent.click(screen.getByRole("button", { name: "Save flow" }));
    expect(await screen.findByText("That isn't valid JSON.")).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("shows the validator's messages when the flow is rejected", async () => {
    server.use(
      http.put(`${API}/suppliers/1/flow`, () =>
        HttpResponse.json({ detail: [{ loc: ["body", "edges", 0], msg: "refers to an unknown node" }] }, { status: 422 }),
      ),
    );
    const editor = await goToFlow();
    await waitFor(() => expect((editor as HTMLTextAreaElement).value).not.toBe(""));
    await userEvent.click(screen.getByRole("button", { name: "Save flow" }));
    expect(await screen.findByText("edges.0: refers to an unknown node")).toBeInTheDocument();
  });

  it("confirms a saved flow", async () => {
    server.use(http.put(`${API}/suppliers/1/flow`, () => HttpResponse.json({ supplier: "supplier-a" })));
    const editor = await goToFlow();
    await waitFor(() => expect((editor as HTMLTextAreaElement).value).not.toBe(""));
    await userEvent.click(screen.getByRole("button", { name: "Save flow" }));
    expect(await screen.findByText("Flow saved.")).toBeInTheDocument();
  });
});

describe("Login and 2FA tab", () => {
  const goToLogin = async (over = {}) => {
    open(over);
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
  };

  it("shows the saved username and that a password exists, never the password", async () => {
    await goToLogin();
    expect(await screen.findByDisplayValue("shop-owner")).toBeInTheDocument();
    expect(screen.getByText("Password saved.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("saves credentials write-only", async () => {
    let body: unknown;
    server.use(
      http.put(`${API}/suppliers/1/credentials`, async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await goToLogin();
    await screen.findByDisplayValue("shop-owner");
    await userEvent.type(screen.getByLabelText("Password"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: "Save credentials" }));
    await waitFor(() => expect(body).toEqual({ username: "shop-owner", password: "hunter2" }));
  });

  it("requires a password to save", async () => {
    await goToLogin();
    await screen.findByDisplayValue("shop-owner");
    await userEvent.click(screen.getByRole("button", { name: "Save credentials" }));
    expect(await screen.findByText("Enter the password.")).toBeInTheDocument();
  });

  it("starts a login on demand and shows the session age", async () => {
    let started = false;
    server.use(http.post(`${API}/suppliers/1/login`, () => ((started = true), new HttpResponse(null, { status: 202 }))));
    await goToLogin();
    expect(await screen.findByText("Session age: 2 h")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(started).toBe(true));
  });

  it("offers a retry only while the Supplier is paused, with the reason", async () => {
    let retried = false;
    server.use(http.post(`${API}/suppliers/1/retry`, () => ((retried = true), new HttpResponse(null, { status: 204 }))));
    await goToLogin({ paused: true, health: "paused", pause_reason: "Wrong code twice" });
    expect(await screen.findByText("Paused: Wrong code twice")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry login" }));
    await waitFor(() => expect(retried).toBe(true));
  });

  it("has no retry button for a Supplier that is not paused", async () => {
    await goToLogin();
    await screen.findByText("Session age: 2 h");
    expect(screen.queryByRole("button", { name: "Retry login" })).not.toBeInTheDocument();
  });

  it("starts a private manual login and opens the ready browser", async () => {
    let started = false;
    const ready = {
      id: 7,
      state: "ready",
      expires_at: "2026-11-03T12:10:00Z",
      browser_url: "http://127.0.0.1:6080/vnc.html",
      error: null,
    };
    open();
    server.use(
      http.get(`${API}/suppliers/1/manual-login`, () =>
        HttpResponse.json({ enabled: true, session: started ? ready : null }),
      ),
      http.post(`${API}/suppliers/1/manual-login`, () => {
        started = true;
        return HttpResponse.json(ready, { status: 201 });
      }),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
    await userEvent.click(await screen.findByRole("button", { name: "Manual login" }));
    expect(await screen.findByRole("link", { name: "Open private browser" })).toHaveAttribute(
      "href", "http://127.0.0.1:6080/vnc.html",
    );
    expect(screen.getByText(/SSH tunnel/)).toBeInTheDocument();
  });

  it("cancels a ready private browser session", async () => {
    let cancelled = false;
    open();
    server.use(
      http.get(`${API}/suppliers/1/manual-login`, () =>
        HttpResponse.json({
          enabled: true,
          session: {
            id: 8,
            state: "ready",
            expires_at: "2026-11-03T12:10:00Z",
            browser_url: "http://127.0.0.1:6080/vnc.html",
            error: null,
          },
        }),
      ),
      http.delete(`${API}/suppliers/1/manual-login`, () => {
        cancelled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel manual login" }));
    await waitFor(() => expect(cancelled).toBe(true));
  });

  const manualSession = (state: string, error: string | null = null) => ({
    enabled: true,
    session: {
      id: 9,
      state,
      expires_at: "2026-11-03T12:10:00Z",
      browser_url: "http://127.0.0.1:6080/vnc.html",
      error,
    },
  });

  it("tells the worker the login is finished when you press Done", async () => {
    let finished = false;
    open();
    server.use(
      http.get(`${API}/suppliers/1/manual-login`, () => HttpResponse.json(manualSession("ready"))),
      http.post(`${API}/suppliers/1/manual-login/finish`, () => {
        finished = true;
        return new HttpResponse(null, { status: 202 });
      }),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
    expect(await screen.findByText(/press Done/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Done, I'm logged in" }));
    await waitFor(() => expect(finished).toBe(true));
  });

  it.each(["finishing", "verifying"])("shows that the login is being checked while %s", async (state) => {
    open();
    server.use(
      http.get(`${API}/suppliers/1/manual-login`, () => HttpResponse.json(manualSession(state))),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
    expect(await screen.findByText(/Checking your login/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done, I'm logged in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Manual login/ })).not.toBeInTheDocument();
  });

  it("shows why the check failed and offers another try", async () => {
    open();
    server.use(
      http.get(`${API}/suppliers/1/manual-login`, () =>
        HttpResponse.json(manualSession("failed", "Not logged in: press Done after login")),
      ),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Login and 2FA" }));
    expect(await screen.findByText(/Not logged in: press Done after login/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Manual login again" })).toBeInTheDocument();
  });
});

it("lists runs and can start a check now", async () => {
  let checked = false;
  server.use(http.post(`${API}/suppliers/1/check`, () => ((checked = true), new HttpResponse(null, { status: 202 }))));
  open();
  await userEvent.click(await screen.findByRole("tab", { name: "Runs" }));
  expect(await screen.findByText("120 listings read")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Check now" }));
  await waitFor(() => expect(checked).toBe(true));
});

describe("Settings tab", () => {
  it("saves the Supplier's website URL and rules", async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.patch(`${API}/suppliers/1`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(supplier());
      }),
    );
    open();
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const siteUrl = await screen.findByLabelText("Site URL");
    expect(siteUrl).toHaveValue("https://supplier-a.example");
    await userEvent.clear(siteUrl);
    await userEvent.type(siteUrl, "https://new-supplier.example");
    const reads = await screen.findByLabelText("Out of Stock reads to confirm");
    expect(reads).toHaveValue(2);
    await userEvent.clear(reads);
    await userEvent.type(reads, "3");
    await userEvent.click(screen.getByLabelText("Treat a removed Listing as Unknown"));
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(body).toMatchObject({
      site_url: "https://new-supplier.example",
      out_confirm_reads: 3,
      removed_as_unknown: true,
      interval_min: 180,
      max_quantity: 100,
    }));
  });

  it("requires a full website URL", async () => {
    open();
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const siteUrl = await screen.findByLabelText("Site URL");
    await userEvent.clear(siteUrl);
    await userEvent.type(siteUrl, "supplier.example");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Enter a full address, like https://supplier.example.")).toBeInTheDocument();
  });

  it("rejects a number below one", async () => {
    open();
    await userEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    const cap = await screen.findByLabelText("Maximum quantity");
    await userEvent.clear(cap);
    await userEvent.type(cap, "0");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Enter a whole number, 1 or more.")).toBeInTheDocument();
  });
});
