import type { Listing } from "../../api/types";
import { Pill } from "../../components/ui/Pill";

/** One mark per Listing: In Stock stays plain; trouble gets a pill. */
export function StatusMark({ listing }: { listing: Pick<Listing, "status" | "removed"> }) {
  if (listing.removed) return <Pill tone="negative">Listing removed</Pill>;
  if (listing.status === "out_of_stock") return <Pill tone="negative">Out of stock</Pill>;
  if (listing.status === "unknown") return <Pill tone="neutral">Unknown</Pill>;
  return <span className="text-muted">In stock</span>;
}

/** "Last updated 09:14." for an error message, or nothing when there was never a good load. */
export function lastGood(stamp: number | undefined): string {
  return stamp ? ` Last updated ${new Date(stamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}.` : "";
}
