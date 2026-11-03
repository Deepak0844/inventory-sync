import { headline } from "./headline";

const sup = (name: string, health: "healthy" | "needs_code" | "paused" | "blocked" | "stale") => ({
  id: 1, name, health, last_success_at: null,
});

it("states the sold out count first", () => {
  expect(headline(14, [])).toBe("14 variants are sold out.");
});

it("uses the singular for one and a plain sentence for none", () => {
  expect(headline(1, [])).toBe("1 variant is sold out.");
  expect(headline(0, [])).toBe("No variants are sold out.");
});

it("names a Supplier that needs a code", () => {
  expect(headline(14, [sup("Supplier B", "needs_code")])).toBe(
    "14 variants are sold out. Supplier B needs a code.",
  );
});

it("says what is wrong with each Supplier that needs attention, healthy ones stay silent", () => {
  const list = [sup("A", "healthy"), sup("B", "paused"), sup("C", "blocked")];
  expect(headline(0, list)).toBe("No variants are sold out. B is paused. C is blocked.");
  expect(headline(0, [sup("D", "stale")])).toBe("No variants are sold out. D has not been checked recently.");
});

it("names two Suppliers then counts the rest", () => {
  const list = [sup("A", "paused"), sup("B", "paused"), sup("C", "paused"), sup("D", "paused")];
  expect(headline(3, list)).toBe("3 variants are sold out. A is paused. B is paused. 2 more need attention.");
});
