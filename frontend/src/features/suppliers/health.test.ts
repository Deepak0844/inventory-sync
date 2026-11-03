import { healthMark } from "./health";

it("healthy Suppliers carry no pill", () => {
  expect(healthMark("healthy")).toEqual({ label: "Healthy", tone: null });
});

it.each([
  ["needs_code", "Needs code", "warning"],
  ["stale", "Stale", "warning"],
  ["paused", "Paused", "negative"],
  ["blocked", "Blocked", "negative"],
] as const)("%s is %s (%s)", (health, label, tone) => {
  expect(healthMark(health)).toEqual({ label, tone });
});
