import type { Health } from "../../api/types";
import type { Tone } from "../../components/ui/Pill";

/** Healthy Suppliers stay unmarked (tone null); everything that needs attention gets a pill. */
export function healthMark(health: Health): { label: string; tone: Tone | null } {
  switch (health) {
    case "healthy": return { label: "Healthy", tone: null };
    case "needs_code": return { label: "Needs code", tone: "warning" };
    case "stale": return { label: "Stale", tone: "warning" };
    case "paused": return { label: "Paused", tone: "negative" };
    case "blocked": return { label: "Blocked", tone: "negative" };
  }
}
