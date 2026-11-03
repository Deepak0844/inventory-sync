import type { Health, Overview } from "../../api/types";

type SupplierHealth = Overview["suppliers"][number];

const MENTION = 2;

const problems: Record<Exclude<Health, "healthy">, (name: string) => string> = {
  needs_code: (name) => `${name} needs a code.`,
  paused: (name) => `${name} is paused.`,
  blocked: (name) => `${name} is blocked.`,
  stale: (name) => `${name} has not been checked recently.`,
};

/** The one-sentence finding at the top of Overview: Sold Out first, then what needs attention. */
export function headline(soldOut: number, suppliers: SupplierHealth[]): string {
  const count =
    soldOut === 0
      ? "No variants are sold out."
      : `${soldOut} ${soldOut === 1 ? "variant is" : "variants are"} sold out.`;
  const attention = suppliers.filter((s) => s.health !== "healthy");
  const named = attention.slice(0, MENTION).map((s) => problems[s.health as Exclude<Health, "healthy">](s.name));
  const rest = attention.length - named.length;
  if (rest > 0) named.push(`${rest} more ${rest === 1 ? "needs" : "need"} attention.`);
  return [count, ...named].join(" ");
}
