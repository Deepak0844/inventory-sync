import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse, delay } from "msw";
import type { ReactNode } from "react";
import { Provider } from "react-redux";

import { makeStore } from "../../store";
import { server } from "../../test/server";
import { aRun, base, serveRuns } from "./testRunMocks";
import { useTestRun } from "./useTestRun";

const flow = { supplier: "supplier-a" };
const wrapper = ({ children }: { children: ReactNode }) => <Provider store={makeStore()}>{children}</Provider>;
const setup = () => renderHook(() => useTestRun(3, () => flow, 20), { wrapper });

it("sends the draft flow, the supplier and only the options that were given", async () => {
  const { posted } = serveRuns({ 1: aRun() });
  const { result } = setup();
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.run?.id).toBe(1));
  expect(posted).toEqual([{ supplier_id: 3, flow, mode: "login" }]);
  act(() => result.current.start({ mode: "login", upToNodeId: "n4" }));
  await waitFor(() => expect(posted).toHaveLength(2));
  expect(posted[1]).toEqual({ supplier_id: 3, flow, mode: "login", up_to_node_id: "n4" });
  act(() => result.current.start({ mode: "extract", listingUrl: "https://s.test/p/1" }));
  await waitFor(() => expect(posted).toHaveLength(3));
  expect(posted[2]).toEqual({ supplier_id: 3, flow, mode: "extract", listing_url: "https://s.test/p/1" });
});

it("reads the draft flow when the run starts, not when the hook renders", async () => {
  serveRuns({ 1: aRun() });
  const getDraft = vi.fn(() => flow);
  const { result } = renderHook(() => useTestRun(3, getDraft, 20), { wrapper });
  expect(getDraft).not.toHaveBeenCalled();
  act(() => result.current.start({ mode: "login" }));
  expect(getDraft).toHaveBeenCalledTimes(1);
});

it("keeps polling while the run is queued, running or waiting for a code, then stops", async () => {
  const { gets } = serveRuns({
    1: [aRun({ state: "queued" }), aRun({ state: "running" }), aRun({ state: "waiting_for_code" }), aRun({ state: "done" })],
  });
  const { result } = setup();
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.run?.state).toBe("done"), { timeout: 10000 });
  const atDone = gets[1];
  expect(atDone).toBe(4);
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(gets[1]).toBe(atDone);
  expect(result.current.busy).toBe(false);
});

it("is busy while a run is in progress", async () => {
  serveRuns({ 1: aRun({ state: "running" }) });
  const { result } = setup();
  expect(result.current.busy).toBe(false);
  act(() => result.current.start({ mode: "login" }));
  expect(result.current.busy).toBe(true);
  await waitFor(() => expect(result.current.run?.state).toBe("running"));
  expect(result.current.busy).toBe(true);
});

it("reports validation errors from the draft and starts no run", async () => {
  server.use(
    http.post(`${base}/test-runs`, () =>
      HttpResponse.json({ detail: [{ loc: ["body", "flow", "nodes", 0, "url"], msg: "must not be empty" }] }, { status: 422 }),
    ),
  );
  const { result } = setup();
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.startErrors).toEqual(["flow.nodes.0.url: must not be empty"]));
  expect(result.current.run).toBeNull();
  expect(result.current.busy).toBe(false);
});

it("clears old start errors when a new run starts", async () => {
  let first = true;
  server.use(
    http.post(`${base}/test-runs`, () =>
      first ? ((first = false), HttpResponse.json({ detail: "flow has a cycle" }, { status: 422 })) : HttpResponse.json({ id: 1 }, { status: 202 }),
    ),
    http.get(`${base}/test-runs/1`, () => HttpResponse.json(aRun())),
  );
  const { result } = setup();
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.startErrors).toEqual(["flow has a cycle"]));
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.run?.id).toBe(1));
  expect(result.current.startErrors).toEqual([]);
});

describe("an old run never replaces a newer one", () => {
  it("ignores the answer to an earlier start that arrives late", async () => {
    let call = 0;
    server.use(
      http.post(`${base}/test-runs`, async () => {
        const mine = ++call;
        if (mine === 1) await delay(150);
        return HttpResponse.json({ id: mine }, { status: 202 });
      }),
      http.get(`${base}/test-runs/:id`, ({ params }) => HttpResponse.json(aRun({ id: Number(params.id), login_result: `run-${params.id}` }))),
    );
    const { result } = setup();
    act(() => result.current.start({ mode: "login" }));
    act(() => result.current.start({ mode: "login" }));
    await waitFor(() => expect(result.current.run?.id).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(result.current.run?.id).toBe(2);
    expect(result.current.run?.login_result).toBe("run-2");
  });

  it("ignores a poll result for the earlier run that arrives after the next run started", async () => {
    let starts = 0;
    server.use(
      http.post(`${base}/test-runs`, () => HttpResponse.json({ id: ++starts }, { status: 202 })),
      http.get(`${base}/test-runs/1`, async () => {
        await delay(200);
        return HttpResponse.json(aRun({ id: 1, state: "failed", error: "the first run" }));
      }),
      http.get(`${base}/test-runs/2`, () => HttpResponse.json(aRun({ id: 2, login_result: "run-2" }))),
    );
    const { result } = setup();
    act(() => result.current.start({ mode: "login" }));
    await waitFor(() => expect(starts).toBe(1));
    act(() => result.current.start({ mode: "login" }));
    await waitFor(() => expect(result.current.run?.id).toBe(2));
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(result.current.run?.id).toBe(2);
    expect(result.current.run?.error).toBeNull();
  });
});

it("shows nothing for a new run until it has loaded, never the previous run's result", async () => {
  let starts = 0;
  server.use(
    http.post(`${base}/test-runs`, () => HttpResponse.json({ id: ++starts }, { status: 202 })),
    http.get(`${base}/test-runs/1`, () => HttpResponse.json(aRun({ id: 1, login_result: "run-1" }))),
    http.get(`${base}/test-runs/2`, async () => {
      await delay(250);
      return HttpResponse.json(aRun({ id: 2, login_result: "run-2" }));
    }),
  );
  const { result } = setup();
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.run?.id).toBe(1));
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(starts).toBe(2));
  await new Promise((resolve) => setTimeout(resolve, 60)); // run 2 is started and still loading
  expect(result.current.run).toBeNull();
  expect(result.current.busy).toBe(true);
  await waitFor(() => expect(result.current.run?.id).toBe(2));
});

it("keeps the latest snapshot while later runs have none", async () => {
  const snapshot = { screenshot_url: `${base}/s.png`, html_url: `${base}/s.html` };
  serveRuns({ 1: aRun({ id: 1, snapshot }), 2: aRun({ id: 2, snapshot: null }) }, [1, 2]);
  const { result } = setup();
  act(() => result.current.start({ mode: "login", upToNodeId: "n4" }));
  await waitFor(() => expect(result.current.snapshot?.snapshot).toEqual(snapshot));
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.run?.id).toBe(2));
  expect(result.current.snapshot?.snapshot).toEqual(snapshot);
  expect(result.current.snapshot?.runId).toBe(1);
});

it("reports a failed poll and recovers on retry", async () => {
  let gets = 0;
  server.use(
    http.post(`${base}/test-runs`, () => HttpResponse.json({ id: 1 }, { status: 202 })),
    http.get(`${base}/test-runs/1`, () => (++gets === 1 ? new HttpResponse(null, { status: 500 }) : HttpResponse.json(aRun()))),
  );
  const { result } = renderHook(() => useTestRun(3, () => flow, 100000), { wrapper });
  act(() => result.current.start({ mode: "login" }));
  await waitFor(() => expect(result.current.pollError).toBe(true));
  expect(result.current.busy).toBe(false);
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.run?.state).toBe("done"));
  expect(result.current.pollError).toBe(false);
});
