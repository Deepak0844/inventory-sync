import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { api } from "../../api/api";
import { makeStore } from "../../store";
import { API, supplier } from "../suppliers/testData";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { FlowBuilder } from "./FlowBuilder";
import { sampleFlow } from "./testData";
import { installBrowserShims } from "./testSupport";
import type { SelectorColumnProps } from "./SelectorColumn";

/** `null` is how the API says the Supplier has no flow yet; any other status is a real error. */
const serve = (flow: Record<string, unknown> | null = sampleFlow() as never, status = 200) => {
  server.use(
    http.get(`${API}/suppliers/1`, () => HttpResponse.json(supplier())),
    http.get(`${API}/suppliers/1/flow`, () =>
      status === 200 ? HttpResponse.json(flow) : HttpResponse.json({ detail: "Server error" }, { status }),
    ),
  );
};
const open = (Panel?: (p: SelectorColumnProps) => React.ReactNode) =>
  renderApp(<FlowBuilder supplierId={1} SelectorPanel={Panel} />, "/flows/1");

beforeEach(() => installBrowserShims());

it("shows the saved flow's steps once it has loaded", async () => {
  serve();
  open();
  expect(await screen.findByText("https://supplier-a.example/login")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Supplier A/ })).toBeInTheDocument();
});

it("shows an error with Retry when the flow cannot be loaded", async () => {
  serve(null, 500);
  open();
  expect(await screen.findByText(/Couldn't load the flow/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

it("starts a Supplier with no flow from a login outline and says so", async () => {
  serve(null);
  open();
  expect(await screen.findByText("https://supplier-a.example/login")).toBeInTheDocument();
  expect(screen.getByText(/No flow yet/)).toBeInTheDocument();
});

it("has nothing to save until something changes", async () => {
  serve();
  open();
  await screen.findByText("https://supplier-a.example/login");
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Revert" })).toBeDisabled();
});

it("saves the flow that was edited and then reports it saved", async () => {
  serve();
  let sent: unknown;
  server.use(
    http.put(`${API}/suppliers/1/flow`, async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json(sent as Record<string, unknown>);
    }),
  );
  open();
  const path = await screen.findByLabelText("Login page path");
  await userEvent.clear(path);
  await userEvent.type(path, "/signin");
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Flow saved.")).toBeInTheDocument();
  expect(sent).toEqual({ ...sampleFlow(), login_path: "/signin" });
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

it("saves from the selected step's inspector", async () => {
  serve();
  let sent: unknown;
  server.use(
    http.put(`${API}/suppliers/1/flow`, async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json(sent as Record<string, unknown>);
    }),
  );
  open();
  fireEvent.click(await screen.findByText("button[type=submit]"));
  const selector = await screen.findByLabelText("Selector");
  await userEvent.clear(selector);
  await userEvent.type(selector, "button.login");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByText("Flow saved.")).toBeInTheDocument();
  expect((sent as { nodes: Array<{ id: string; selector?: string }> }).nodes)
    .toContainEqual(expect.objectContaining({ id: "n4", selector: "button.login" }));
});

it("shows the server's reasons when it refuses the flow", async () => {
  serve();
  server.use(
    http.put(`${API}/suppliers/1/flow`, () =>
      HttpResponse.json({ detail: [{ loc: ["body", "nodes", 3], msg: "Value error, node n4 is broken" }] }, { status: 422 }),
    ),
  );
  open();
  const path = await screen.findByLabelText("Login page path");
  await userEvent.type(path, "x");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect((await screen.findAllByText(/node n4 is broken/)).length).toBeGreaterThan(0);
});

it("puts back the saved flow on Revert", async () => {
  serve();
  open();
  const path = await screen.findByLabelText("Login page path");
  await userEvent.type(path, "x");
  await userEvent.click(screen.getByRole("button", { name: "Revert" }));
  expect(await screen.findByLabelText("Login page path")).toHaveValue("/login");
  expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
});

it("counts the problems that prevent the flow from running", async () => {
  const flow = sampleFlow();
  (flow.nodes[3] as { selector: string }).selector = "";
  serve(flow as never);
  open();
  expect(await screen.findByText("Fix 1 problem before this flow can run")).toBeInTheDocument();
  expect(screen.getByText("Pick or enter a selector.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
});

it("saves a completed step as a draft while the rest of the flow is incomplete", async () => {
  const flow = sampleFlow();
  flow.nodes = flow.nodes.slice(0, -2);
  flow.edges = flow.edges.slice(0, -2);
  serve(flow as never);
  let sent: unknown;
  server.use(http.put(`${API}/suppliers/1/flow`, async ({ request }) => {
    sent = await request.json();
    return HttpResponse.json(sent as Record<string, unknown>);
  }));
  open();
  fireEvent.click(await screen.findByText("button[type=submit]"));
  await userEvent.type(screen.getByLabelText("Selector"), "x");
  const save = screen.getByRole("button", { name: "Save changes" });
  expect(save).toBeEnabled();
  await userEvent.click(save);
  expect(await screen.findByText(/Draft saved/)).toBeInTheDocument();
  expect((sent as { nodes: Array<{ id: string; selector?: string }> }).nodes)
    .toContainEqual(expect.objectContaining({ id: "n4", selector: "button[type=submit]x" }));
});

it("adds a step from the palette, connected after the last one", async () => {
  serve();
  open();
  await screen.findByText("https://supplier-a.example/login");
  await userEvent.click(screen.getByRole("button", { name: "Branch" }));
  expect(screen.getByText("No element chosen")).toBeInTheDocument();
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
});

it("fills the field that is waiting when a selector is picked", async () => {
  serve();
  const panel = ({ onPickSelector, selectedNodeId }: SelectorColumnProps) => (
    <button onClick={() => onPickSelector("#picked")}>Choose #picked ({selectedNodeId ?? "none"})</button>
  );
  open(panel);
  await screen.findByText("https://supplier-a.example/login");
  // fireEvent: user-event's mousedown has no `view`, which React Flow's drag handling needs in jsdom.
  fireEvent.click(screen.getByText("button[type=submit]"));
  await userEvent.click(await screen.findByRole("button", { name: "Pick selector for Selector" }));
  await userEvent.click(screen.getByRole("button", { name: "Choose #picked (n4)" }));
  await waitFor(() => expect(screen.getByLabelText("Selector")).toHaveValue("#picked"));
  expect(screen.getByRole("button", { name: "Pick selector for Selector" })).toHaveAttribute("aria-pressed", "false");
});

it("fills the selected step's selector when a page element is clicked, without pressing Pick first", async () => {
  serve();
  const panel = ({ onPickSelector }: SelectorColumnProps) => (
    <button onClick={() => onPickSelector("#picked")}>Choose #picked</button>
  );
  open(panel);
  await screen.findByText("https://supplier-a.example/login");
  fireEvent.click(screen.getByText("button[type=submit]"));
  await screen.findByLabelText("Selector");
  await userEvent.click(screen.getByRole("button", { name: "Choose #picked" }));
  await waitFor(() => expect(screen.getByLabelText("Selector")).toHaveValue("#picked"));
});

it("says what to do when a clicked element has nowhere to go", async () => {
  serve();
  const panel = ({ onPickSelector }: SelectorColumnProps) => (
    <button onClick={() => onPickSelector("#picked")}>Choose #picked</button>
  );
  open(panel);
  await screen.findByText("https://supplier-a.example/login");
  await userEvent.click(screen.getByRole("button", { name: "Choose #picked" }));
  expect(await screen.findByText("Press Pick next to a field first, then click the element.")).toBeInTheDocument();
});

describe("pick feedback", () => {
  const labelPanel = ({ onPickSelector, targetLabel }: SelectorColumnProps) => (
    <div>
      <p data-testid="target">{targetLabel === undefined ? "undefined" : targetLabel === null ? "none" : targetLabel}</p>
      <button onClick={() => onPickSelector("#picked")}>Choose #picked</button>
    </div>
  );

  it("tells the panel which step and field a pick will fill", async () => {
    serve();
    open(labelPanel);
    await screen.findByText("https://supplier-a.example/login");
    expect(screen.getByTestId("target")).toHaveTextContent("none");
    fireEvent.click(screen.getByText("button[type=submit]"));
    await screen.findByLabelText("Selector");
    expect(screen.getByTestId("target")).toHaveTextContent("Click step, Selector");
  });

  it("names the stock rule when its Pick button is armed", async () => {
    serve();
    open(labelPanel);
    await screen.findByText("https://supplier-a.example/login");
    await userEvent.click(await screen.findByRole("button", { name: "Pick selector for Stock element" }));
    expect(screen.getByTestId("target")).toHaveTextContent("Stock rules, Stock element");
  });

  it("shows the picked selector on the step's card and flags the field that changed", async () => {
    serve();
    open(labelPanel);
    await screen.findByText("https://supplier-a.example/login");
    fireEvent.click(screen.getByText("button[type=submit]"));
    await screen.findByLabelText("Selector");
    await userEvent.click(screen.getByRole("button", { name: "Choose #picked" }));
    await waitFor(() => expect(screen.getByLabelText("Selector")).toHaveValue("#picked"));
    expect(screen.getByText("#picked", { selector: ".react-flow__node *" })).toBeInTheDocument();
    expect(screen.getByLabelText("Selector").closest("[data-flash]")).not.toBeNull();
  });

  it("stops flagging the field after a couple of seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      serve();
      open(labelPanel);
      await screen.findByText("https://supplier-a.example/login");
      fireEvent.click(screen.getByText("button[type=submit]"));
      await screen.findByLabelText("Selector");
      await userEvent.click(screen.getByRole("button", { name: "Choose #picked" }));
      await waitFor(() => expect(screen.getByLabelText("Selector").closest("[data-flash]")).not.toBeNull());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(screen.getByLabelText("Selector").closest("[data-flash]")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

it("asks before leaving with unsaved changes", async () => {
  serve();
  open();
  await userEvent.type(await screen.findByLabelText("Login page path"), "x");
  await userEvent.click(screen.getByRole("button", { name: "Back to flows" }));
  expect(screen.getByText("Leave without saving?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Stay" }));
  expect(screen.queryByText("Leave without saving?")).not.toBeInTheDocument();
});

it("warns the browser before it closes the tab with unsaved changes", async () => {
  serve();
  open();
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(false);
  await userEvent.type(await screen.findByLabelText("Login page path"), "x");
  const dirty = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(dirty);
  expect(dirty.defaultPrevented).toBe(true);
});

it("is read only on a phone: no palette, no form, no Save", async () => {
  installBrowserShims({ phone: true });
  serve();
  open();
  await screen.findByText("https://supplier-a.example/login");
  expect(screen.getByText(/read-only on a phone/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Branch" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Login page path")).not.toBeInTheDocument();
});


it("asks the server again when opened, so a flow deleted meanwhile is not shown from the cache", async () => {
  const old = sampleFlow() as unknown as { nodes: { url?: string }[] };
  old.nodes[0].url = "https://old.example/OLD-SAVED-LOGIN"; // a URL only the saved flow has
  serve(old as never);
  const store = makeStore();
  await store.dispatch(api.endpoints.flow.initiate(1)).unwrap(); // the flow is now cached
  serve(null); // ...and then removed on the server
  renderApp(<FlowBuilder supplierId={1} SelectorPanel={() => null} />, "/flows/1", store);
  expect(await screen.findByText(/No flow yet/)).toBeInTheDocument();
  expect(screen.queryByText("https://old.example/OLD-SAVED-LOGIN")).not.toBeInTheDocument();
});
