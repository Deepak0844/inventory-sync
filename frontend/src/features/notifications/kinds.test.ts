import type { NotificationKind } from "../../api/types";
import { kindTitle } from "./kinds";

const all: NotificationKind[] = [
  "login_attention", "needs_code", "flow_failure", "pending_approval", "supplier_unreachable",
  "blocked", "listing_removed", "stale_variants", "shopify_error", "daily_summary",
];

it("has a plain-language title for every kind", () => {
  for (const kind of all) expect(kindTitle(kind)).toMatch(/^[A-Z][a-z]/);
});

it("uses the words from the failure table", () => {
  expect(kindTitle("login_attention")).toBe("Login needs attention");
  expect(kindTitle("flow_failure")).toBe("Flow failure");
  expect(kindTitle("pending_approval")).toBe("Waiting for approval");
});
