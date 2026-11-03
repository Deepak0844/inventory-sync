import { http, HttpResponse } from "msw";

import type { TestRun } from "../../api/types";
import { server } from "../../test/server";

export const base = "http://localhost:3000/api";

export function aRun(over: Partial<TestRun> = {}): TestRun {
  return {
    id: 1, state: "done", mode: "login", steps: [], snapshot: null, reading: null,
    login_result: "logged_in", error: null, wrote_to_shopify: false, ...over,
  };
}

/** Serves POST /test-runs (recording each body) and GET /test-runs/:id from `runs`, one entry per call. */
export function serveRuns(runs: Record<number, TestRun | TestRun[]>, started: number[] = [1]) {
  const posted: unknown[] = [];
  const gets: Record<number, number> = {};
  let next = 0;
  server.use(
    http.post(`${base}/test-runs`, async ({ request }) => {
      posted.push(await request.json());
      return HttpResponse.json({ id: started[Math.min(next++, started.length - 1)] }, { status: 202 });
    }),
    http.get(`${base}/test-runs/:id`, ({ params }) => {
      const id = Number(params.id);
      gets[id] = (gets[id] ?? 0) + 1;
      const entry = runs[id];
      const run = Array.isArray(entry) ? entry[Math.min(gets[id] - 1, entry.length - 1)] : entry;
      return HttpResponse.json(run);
    }),
  );
  return { posted, gets };
}
