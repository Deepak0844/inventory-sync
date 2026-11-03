import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { TestRunSnapshot } from "../../api/types";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";
import { SelectorPicker } from "./SelectorPicker";

const base = "http://localhost:3000/api";
const HTML = `<!doctype html><html><body>
<h1 id="title">Trail Shoe</h1><p class="stock-status">Out of stock</p><a href="/x">Cart</a>
</body></html>`;
const snapshot: TestRunSnapshot = {
  screenshot_url: `${base}/test-runs/1/files/step.png`,
  html_url: `${base}/test-runs/1/files/snapshot.html`,
};

function serveHtml(body = HTML) {
  server.use(http.get(snapshot.html_url, () => HttpResponse.text(body)));
}
const frame = () => screen.getByTitle("Page snapshot") as HTMLIFrameElement;
const inFrame = (css: string): Element => {
  const el = frame().contentDocument?.querySelector(css);
  if (!el) throw new Error(`not in the snapshot: ${css}`);
  return el;
};
/**
 * jsdom does not implement iframe `srcdoc`, so do what a browser does with it: write the document
 * into the frame and fire its load event. (jsdom also ignores `sandbox`, so the test can only check
 * the attribute, not that scripts are blocked.)
 */
async function loaded(): Promise<HTMLIFrameElement> {
  const el = (await screen.findByTitle("Page snapshot")) as HTMLIFrameElement;
  const doc = el.contentDocument as Document;
  doc.open();
  doc.write(el.getAttribute("srcdoc") ?? "");
  doc.close();
  fireEvent.load(el);
  return el;
}

it("shows a loading state while the snapshot downloads", () => {
  server.use(http.get(snapshot.html_url, () => new Promise(() => {})));
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  expect(screen.getByTestId("block-loading")).toBeInTheDocument();
});

it("renders the page in a frame that cannot run scripts", async () => {
  serveHtml();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  await loaded();
  expect(frame()).toHaveAttribute("sandbox", "allow-same-origin");
  expect(frame().getAttribute("sandbox")).not.toContain("allow-scripts");
  expect(frame().getAttribute("srcdoc")).toContain("Trail Shoe");
});

it("hovering an element shows the selector a click would pick", async () => {
  serveHtml();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  await loaded();
  expect(screen.getByText("Click an element on the page to pick it.")).toBeInTheDocument();
  fireEvent.mouseOver(inFrame("#title"));
  expect(screen.getByText("Click to pick #title")).toBeInTheDocument();
  expect(inFrame("#title")).toHaveAttribute("data-picker-hover");
  fireEvent.mouseOver(inFrame("a"));
  expect(inFrame("#title")).not.toHaveAttribute("data-picker-hover");
});

it("clicking an element picks its stable selector and leaves the page where it is", async () => {
  serveHtml();
  const onPick = vi.fn();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={onPick} />);
  await loaded();
  const link = inFrame("a");
  const notPrevented = fireEvent.click(link);
  expect(notPrevented).toBe(false);
  expect(onPick).toHaveBeenCalledWith('a:has-text("Cart")');
  expect(screen.getByText('a:has-text("Cart")')).toBeInTheDocument();
  expect(screen.getByText(/^Picked/)).toBeInTheDocument();
  expect(inFrame("a")).not.toHaveAttribute("data-picker-hover");
});

it("avoids text selectors when asked, for elements whose text changes", async () => {
  serveHtml();
  const onPick = vi.fn();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={onPick} avoidText />);
  await loaded();
  fireEvent.click(inFrame(".stock-status"));
  expect(onPick).toHaveBeenCalledWith("p.stock-status");
});

it("offers the screenshot as another view of the same step", async () => {
  serveHtml();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  await loaded();
  await userEvent.click(screen.getByRole("button", { name: "Screenshot" }));
  expect(screen.getByRole("img", { name: "Screenshot of the page at this step" })).toHaveAttribute("src", snapshot.screenshot_url);
  expect(screen.queryByTitle("Page snapshot")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Page" }));
  expect(screen.getByTitle("Page snapshot")).toBeInTheDocument();
});

it("lets you type a selector and says how many elements it matches", async () => {
  serveHtml();
  const onPick = vi.fn();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={onPick} />);
  await loaded();
  const field = screen.getByLabelText("Or type a selector");
  await userEvent.type(field, "#title");
  expect(await screen.findByText("Matches 1 element on this page.")).toBeInTheDocument();
  await userEvent.clear(field);
  await userEvent.type(field, ".nope");
  expect(await screen.findByText("Matches nothing on this page.")).toBeInTheDocument();
  await userEvent.clear(field);
  await userEvent.type(field, "div[["); // user-event reads a single [ as a key descriptor
  expect(await screen.findByText("That isn't a valid selector.")).toBeInTheDocument();
  await userEvent.clear(field);
  await userEvent.type(field, "#title");
  await userEvent.click(screen.getByRole("button", { name: "Use selector" }));
  expect(onPick).toHaveBeenCalledWith("#title");
});

it("cannot use a blank selector", async () => {
  serveHtml();
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  await loaded();
  expect(screen.getByRole("button", { name: "Use selector" })).toBeDisabled();
});

it("shows an error with Retry inside the block when the snapshot cannot be loaded", async () => {
  let calls = 0;
  server.use(
    http.get(snapshot.html_url, () => (calls++ === 0 ? new HttpResponse(null, { status: 500 }) : HttpResponse.text(HTML))),
  );
  renderApp(<SelectorPicker snapshot={snapshot} onPick={() => {}} />);
  expect(await screen.findByText("Couldn't load the page snapshot.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await loaded();
});
