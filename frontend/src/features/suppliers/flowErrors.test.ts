import { flowErrors, parseFlowJson } from "./flowErrors";

it("reads a plain detail string", () => {
  expect(flowErrors({ status: 422, data: { detail: "flow has a cycle" } })).toEqual(["flow has a cycle"]);
});

it("reads FastAPI validation entries with their location", () => {
  const error = { status: 422, data: { detail: [{ loc: ["body", "nodes", 2], msg: "unknown node type" }] } };
  expect(flowErrors(error)).toEqual(["nodes.2: unknown node type"]);
});

it("falls back to a general message for anything else", () => {
  expect(flowErrors({ status: 500, data: null })).toEqual(["Couldn't save the flow. Try again."]);
  expect(flowErrors(undefined)).toEqual(["Couldn't save the flow. Try again."]);
});

it("parses JSON objects and rejects anything else with a readable message", () => {
  expect(parseFlowJson('{"supplier":"a"}')).toEqual({ ok: true, value: { supplier: "a" } });
  expect(parseFlowJson("{oops")).toEqual({ ok: false, message: "That isn't valid JSON." });
  expect(parseFlowJson("[1,2]")).toEqual({ ok: false, message: "A flow is a JSON object." });
});
