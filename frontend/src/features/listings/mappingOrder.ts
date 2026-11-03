import type { Mapping } from "../../api/types";

const byPriority = (m: Mapping[]) => [...m].sort((a, b) => a.priority - b.priority);
const renumber = (m: Mapping[]): Mapping[] => m.map((x, i) => ({ listing_id: x.listing_id, priority: i + 1 }));

/** Move one Listing up or down in priority order, renumbering from 1. At either end nothing moves. */
export function moveMapping(mappings: Mapping[], listingId: number, dir: "up" | "down"): Mapping[] {
  const sorted = byPriority(mappings);
  const from = sorted.findIndex((m) => m.listing_id === listingId);
  const to = dir === "up" ? from - 1 : from + 1;
  if (from < 0 || to < 0 || to >= sorted.length) return renumber(sorted);
  [sorted[from], sorted[to]] = [sorted[to], sorted[from]];
  return renumber(sorted);
}

export function removeMapping(mappings: Mapping[], listingId: number): Mapping[] {
  return renumber(byPriority(mappings).filter((m) => m.listing_id !== listingId));
}

/** Add a Listing as the lowest priority. A Listing that is already mapped is ignored. */
export function addMapping(mappings: Mapping[], listingId: number): Mapping[] {
  if (mappings.some((m) => m.listing_id === listingId)) return mappings;
  return renumber([...byPriority(mappings), { listing_id: listingId, priority: 0 }]);
}
