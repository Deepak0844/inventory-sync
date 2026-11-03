import type { FlaggedOrder } from "../../api/types";
import type { Tone } from "../../components/ui/Pill";

type Reason = FlaggedOrder["reasons"][number];

export const reasonLabel: Record<Reason, { text: string; tone: Tone }> = {
  stale: { text: "Stale", tone: "warning" },
  recently_sold_out: { text: "Sold out recently", tone: "negative" },
  lines_truncated: { text: "Lines truncated", tone: "warning" },
};
