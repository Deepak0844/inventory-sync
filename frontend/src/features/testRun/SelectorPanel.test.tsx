import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { SelectorPanel } from "./SelectorPanel";
import { aRun, base, serveRuns } from "./testRunMocks";

const flow = { supplier: "supplier-a", nodes: [] };
const stepAt = "2026-11-03T10:00:00Z";

function panel(props: Partial<Parameters<typeof SelectorPanel>[0]> = {}) {
  const onPickSelector = vi.fn();
  const getDraftFlow = vi.fn(() => flow);
  renderApp(
    <SelectorPanel supplierId={3} getDraftFlow={getDraftFlow} selectedNodeId="n4" onPickSelector={onPickSelector} pollIntervalMs={20} {...props} />,
  );
  return { onPickSelector, getDraftFlow };
}
const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

describe("before any run", () => {
  it("says what to do, and always says Test runs never write to Shopify", () => {
    panel();
    expect(screen.getByText("Test runs never write to Shopify.")).toBeInTheDocument();
    expect(screen.getByText("No test run yet. Run a login test, take a snapshot, or test a Listing.")).toBeInTheDocument();
    expect(screen.getByText("No snapshot yet. Select a step in the flow and choose Take snapshot here.")).toBeInTheDocument();
  });

  it("cannot take a snapshot without a selected step", () => {
    panel({ selectedNodeId: null });
    expect(screen.getByRole("button", { name: "Take snapshot here" })).toBeDisabled();
    expect(screen.getByText("Select a step in the flow to take a snapshot there.")).toBeInTheDocument();
  });

  it("cannot test a Listing until the address is a full web address", async () => {
    panel();
    const test = screen.getByRole("button", { name: "Test on a Listing" });
    expect(test).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Listing address"), "supplier.test/p/1");
    expect(test).toBeDisabled();
    expect(screen.getByText("Enter the full address, starting with https://")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Listing address"));
    await userEvent.type(screen.getByLabelText("Listing address"), "https://supplier.test/p/1");
    expect(test).toBeEnabled();
  });
});

describe("login test", () => {
  it("runs the draft flow and lists each step", async () => {
    const { posted } = serveRuns({
      1: aRun({
        steps: [
          { node_id: "n1", type: "goto", ok: true, error: null, screenshot_url: null, at: stepAt },
          { node_id: "n2", type: "fill", ok: true, error: null, screenshot_url: null, at: stepAt },
        ],
        login_result: "logged_in",
      }),
    });
    const { getDraftFlow } = panel();
    expect(getDraftFlow).not.toHaveBeenCalled();
    await click("Run login test");
    expect(await screen.findByText("Go to URL")).toBeInTheDocument();
    expect(screen.getByText("Fill")).toBeInTheDocument();
    expect(screen.getByText("Login: Logged in")).toBeInTheDocument();
    expect(posted).toEqual([{ supplier_id: 3, flow, mode: "login" }]);
  });

  it("marks a failed step with its error", async () => {
    serveRuns({
      1: aRun({
        state: "failed",
        error: "The run stopped at n3.",
        login_result: "flow_failure",
        steps: [
          { node_id: "n3", type: "click", ok: false, error: "Nothing matched button.go", screenshot_url: null, at: stepAt },
        ],
      }),
    });
    panel();
    await click("Run login test");
    expect(await screen.findByText("Nothing matched button.go")).toBeInTheDocument();
    const step = screen.getByText("Click").closest("li") as HTMLElement;
    expect(within(step).getByText("Failed")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("The run stopped at n3.");
  });

  it("shows a step's screenshot larger when its thumbnail is clicked", async () => {
    serveRuns({
      1: aRun({ steps: [{ node_id: "n1", type: "goto", ok: true, error: null, screenshot_url: `${base}/test-runs/1/files/n1.png`, at: stepAt }] }),
    });
    panel();
    await click("Run login test");
    const toggle = await screen.findByRole("button", { name: "Show screenshot of step n1" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(screen.getByRole("img", { name: "Screenshot after step n1" })).toHaveAttribute("src", `${base}/test-runs/1/files/n1.png`);
    await userEvent.click(screen.getByRole("button", { name: "Hide screenshot of step n1" }));
    expect(screen.queryByRole("img", { name: "Screenshot after step n1" })).not.toBeInTheDocument();
  });
});

describe("while a run is going", () => {
  it("walks through queued, running and done, and locks the buttons while it goes", async () => {
    serveRuns({ 1: [aRun({ state: "queued" }), aRun({ state: "running" }), aRun({ state: "done" })] });
    panel();
    await click("Run login test");
    expect(await screen.findByText("Queued")).toBeInTheDocument();
    for (const name of ["Run login test", "Take snapshot here"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(await screen.findByText("Done")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run login test" })).toBeEnabled();
  });

  it("points at the needs-code card while waiting for a Login Code", async () => {
    serveRuns({ 1: [aRun({ state: "waiting_for_code" }), aRun({ state: "done" })] });
    panel();
    await click("Run login test");
    expect(await screen.findByText("Waiting for a code")).toBeInTheDocument();
    expect(screen.getByText("Paste the code in the card at the top of the page. The run carries on when it arrives.")).toBeInTheDocument();
    expect(await screen.findByText("Done")).toBeInTheDocument();
    expect(screen.queryByText(/Paste the code/)).not.toBeInTheDocument();
  });
});

describe("snapshot", () => {
  it("runs to the selected step, then lets you pick an element on the page", async () => {
    const html = `${base}/test-runs/1/files/snapshot.html`;
    const { posted } = serveRuns({ 1: aRun({ snapshot: { screenshot_url: `${base}/test-runs/1/files/s.png`, html_url: html } }) });
    server.use(http.get(html, () => HttpResponse.text(`<!doctype html><html><body><h1 id="title">Trail Shoe</h1></body></html>`)));
    const { onPickSelector } = panel();
    await click("Take snapshot here");
    expect(posted).toEqual([{ supplier_id: 3, flow, mode: "login", up_to_node_id: "n4" }]);
    const frame = (await screen.findByTitle("Page snapshot")) as HTMLIFrameElement;
    const doc = frame.contentDocument as Document; // jsdom has no srcdoc: write it as a browser would
    doc.open();
    doc.write(frame.getAttribute("srcdoc") ?? "");
    doc.close();
    fireEvent.load(frame);
    fireEvent.click(doc.getElementById("title") as Element);
    expect(onPickSelector).toHaveBeenCalledWith("#title");
  });
});

describe("test on a Listing", () => {
  async function runExtract(reading: Parameters<typeof aRun>[0]) {
    const { posted } = serveRuns({ 1: aRun({ mode: "extract", login_result: null, ...reading }) });
    panel();
    await userEvent.type(screen.getByLabelText("Listing address"), "https://supplier.test/p/1");
    await click("Test on a Listing");
    return posted;
  }

  it("shows the reading, the rule that matched and the quantity in plain words", async () => {
    const posted = await runExtract({
      reading: { result: "in_stock", error_kind: null, quantity: 7, matched_rule: 'in_stock_if contains "in stock"' },
    });
    expect(await screen.findByText("In stock")).toBeInTheDocument();
    expect(screen.getByText('Matched rule: in_stock_if contains "in stock"')).toBeInTheDocument();
    expect(screen.getByText("Quantity: 7")).toBeInTheDocument();
    expect(posted).toEqual([{ supplier_id: 3, flow, mode: "extract", listing_url: "https://supplier.test/p/1" }]);
  });

  it("says why a reading is Unknown, and shows a dash for a missing quantity", async () => {
    await runExtract({ reading: { result: "unknown", error_kind: "flow_failure", quantity: null, matched_rule: null } });
    expect(await screen.findByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("The stock element wasn't found on the page.")).toBeInTheDocument();
    expect(screen.getByText("No rule matched.")).toBeInTheDocument();
    expect(screen.getByText("Quantity: –")).toBeInTheDocument();
  });

  it("says a removed Listing is removed", async () => {
    await runExtract({ reading: { result: "listing_removed", error_kind: null, quantity: null, matched_rule: null } });
    expect(await screen.findByText("Listing removed")).toBeInTheDocument();
  });
});

describe("when something goes wrong", () => {
  it("shows the draft's validation errors where the buttons are", async () => {
    server.use(
      http.post(`${base}/test-runs`, () =>
        HttpResponse.json({ detail: [{ loc: ["body", "flow", "nodes", 0, "url"], msg: "must not be empty" }] }, { status: 422 }),
      ),
    );
    panel();
    await click("Run login test");
    expect(await screen.findByRole("alert")).toHaveTextContent("flow.nodes.0.url: must not be empty");
    expect(screen.getByText("No test run yet. Run a login test, take a snapshot, or test a Listing.")).toBeInTheDocument();
  });

  it("shows an error with Retry inside the block when the run cannot be read", async () => {
    let gets = 0;
    server.use(
      http.post(`${base}/test-runs`, () => HttpResponse.json({ id: 1 }, { status: 202 })),
      http.get(`${base}/test-runs/1`, () => (++gets === 1 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(aRun({ state: "done" })))),
    );
    panel({ pollIntervalMs: 100000 });
    await click("Run login test");
    expect(await screen.findByText("Couldn't load the test run.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Done")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Couldn't load the test run.")).not.toBeInTheDocument());
  });
});

it("hands avoidText on to the picker", async () => {
  const html = `${base}/test-runs/1/files/snapshot.html`;
  serveRuns({ 1: aRun({ snapshot: { screenshot_url: `${base}/s.png`, html_url: html } }) });
  server.use(http.get(html, () => HttpResponse.text(`<!doctype html><html><body><p class="stock-status">Out of stock</p></body></html>`)));
  const { onPickSelector } = panel({ avoidText: true });
  await click("Take snapshot here");
  const frame = (await screen.findByTitle("Page snapshot")) as HTMLIFrameElement;
  const doc = frame.contentDocument as Document;
  doc.open();
  doc.write(frame.getAttribute("srcdoc") ?? "");
  doc.close();
  fireEvent.load(frame);
  fireEvent.click(doc.querySelector("p") as Element);
  expect(onPickSelector).toHaveBeenCalledWith("p.stock-status");
});
