import { describeRedStrip } from "./redStrip";

const NOW = Date.parse("2026-11-03T12:00:00Z");

it("shows nothing when no Supplier is overdue", () => {
  expect(describeRedStrip([], NOW)).toBeNull();
});

it("names one Supplier and how long ago it last succeeded", () => {
  const text = describeRedStrip(
    [{ supplier_id: 1, supplier_name: "Supplier B", last_success_at: "2026-11-03T07:00:00Z" }],
    NOW,
  );
  expect(text).toBe("Supplier B: last successful check 5 h ago");
});

it("names several Suppliers", () => {
  const text = describeRedStrip(
    [
      { supplier_id: 1, supplier_name: "A", last_success_at: "2026-11-03T11:30:00Z" },
      { supplier_id: 2, supplier_name: "B", last_success_at: "2026-11-02T12:00:00Z" },
    ],
    NOW,
  );
  expect(text).toBe("A: last successful check 30 min ago. B: last successful check 1 d ago");
});

it("says never when a Supplier has no successful check", () => {
  const text = describeRedStrip(
    [{ supplier_id: 1, supplier_name: "A", last_success_at: null }],
    NOW,
  );
  expect(text).toBe("A: no successful check yet");
});
