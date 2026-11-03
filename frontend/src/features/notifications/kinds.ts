import type { NotificationKind } from "../../api/types";
import type { Tone } from "../../components/ui/Pill";

const kinds: Record<NotificationKind, { title: string; tone: Tone }> = {
  login_attention: { title: "Login needs attention", tone: "warning" },
  needs_code: { title: "Needs code", tone: "warning" },
  flow_failure: { title: "Flow failure", tone: "negative" },
  pending_approval: { title: "Waiting for approval", tone: "warning" },
  supplier_unreachable: { title: "Supplier unreachable", tone: "negative" },
  blocked: { title: "Blocked", tone: "negative" },
  listing_removed: { title: "Listing removed", tone: "warning" },
  stale_variants: { title: "Stale variants", tone: "warning" },
  shopify_error: { title: "Shopify error", tone: "negative" },
  daily_summary: { title: "Daily summary", tone: "neutral" },
};

/** What the notification is, in the words of the failure table in PLAN.md. */
export const kindTitle = (kind: NotificationKind): string => kinds[kind].title;
/** Red for things that are broken, amber for things waiting on you. */
export const kindTone = (kind: NotificationKind): Tone => kinds[kind].tone;
