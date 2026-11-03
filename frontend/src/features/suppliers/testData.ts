import type { Supplier } from "../../api/types";

export const API = "http://localhost:3000/api";

export function supplier(over: Partial<Supplier> = {}): Supplier {
  return {
    id: 1,
    name: "Supplier A",
    site_url: "https://supplier-a.example",
    stock_source: "scrape",
    interval_min: 180,
    out_confirm_reads: 2,
    in_confirm_reads: 1,
    confirm_gap_min: 30,
    removed_as_unknown: false,
    max_quantity: 100,
    two_fa_methods: ["ui_code"],
    code_window_min: 10,
    paused: false,
    pause_reason: null,
    health: "healthy",
    last_success_at: new Date(Date.now() - 30 * 60_000).toISOString(),
    session_age_s: 7200,
    listing_count: 120,
    ...over,
  };
}
