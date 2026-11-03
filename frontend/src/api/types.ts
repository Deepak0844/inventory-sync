// Mirrors docs/api.md. Times are ISO 8601 UTC strings.

export type Health = "healthy" | "needs_code" | "paused" | "stale" | "blocked";
export type TwoFaMethod = "ui_code" | "email_code";
export type VariantState = "available" | "sold_out" | null;
export type ReadingResult = "in_stock" | "out_of_stock" | "unknown";

export interface Supplier {
  id: number;
  name: string;
  site_url: string;
  stock_source: "scrape" | "feed";
  interval_min: number;
  out_confirm_reads: number;
  in_confirm_reads: number;
  confirm_gap_min: number;
  removed_as_unknown: boolean;
  max_quantity: number;
  two_fa_methods: TwoFaMethod[];
  code_window_min: number;
  paused: boolean;
  pause_reason: string | null;
  health: Health;
  last_success_at: string | null;
  session_age_s: number | null;
  listing_count: number;
}
export type NewSupplier = Pick<Supplier, "name" | "site_url" | "interval_min"> &
  Partial<Omit<Supplier, "id">>;

export interface SupplierCredentials {
  username: string;
  has_password: boolean;
}

export interface ManualLogin {
  id: number;
  state:
    | "queued" | "ready" | "finishing" | "verifying"
    | "succeeded" | "failed" | "expired" | "cancelled";
  expires_at: string;
  browser_url: string;
  error: string | null;
}

export interface ManualLoginStatus {
  enabled: boolean;
  session: ManualLogin | null;
}

export interface Run {
  id: number;
  kind: string;
  state: string;
  started_at: string;
  finished_at: string | null;
  summary: string;
}

export interface PendingCode {
  supplier_id: number;
  supplier_name: string;
  expires_at: string;
}

export interface Listing {
  id: number;
  supplier_id: number;
  url: string;
  selection_hint: string | null;
  status: ReadingResult;
  quantity: number | null;
  removed: boolean;
  last_success_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  next_cursor: string | null;
}

export interface ListingQuery {
  supplier_id?: number;
  q?: string;
  status?: ReadingResult;
  cursor?: string;
  limit?: number;
}

export interface ImportResult {
  created: number;
  updated: number;
  errors: { row: number; message: string }[];
}

export interface VariantRow {
  id: number;
  shopify_variant_id: string;
  sku: string;
  title: string;
  state: VariantState;
  sold_out_at: string | null;
  stale: boolean;
  listings: { listing_id: number; supplier_id: number; priority: number }[];
  readings: { result: ReadingResult; read_at: string }[];
}

export interface VariantQuery {
  state?: "available" | "sold_out";
  stale?: boolean;
  q?: string;
  cursor?: string;
  limit?: number;
}

export interface Mapping {
  listing_id: number;
  priority: number;
}

export interface Approval {
  id: number;
  supplier_id: number;
  supplier_name: string;
  created_at: string;
  changes: { variant_id: number; sku: string; from_state: VariantState; to_state: VariantState }[];
}

export type NotificationKind =
  | "login_attention"
  | "needs_code"
  | "flow_failure"
  | "pending_approval"
  | "supplier_unreachable"
  | "blocked"
  | "listing_removed"
  | "stale_variants"
  | "shopify_error"
  | "daily_summary";

export interface AppNotification {
  id: number;
  kind: NotificationKind;
  supplier_id: number | null;
  supplier_name: string | null;
  message: string;
  created_at: string;
  resolved_at: string | null;
  screenshot_url: string | null;
}

export interface FlaggedOrder {
  order_id: string;
  name: string;
  created_at: string;
  reasons: ("stale" | "recently_sold_out" | "lines_truncated")[];
  variants: { sku: string; reason: string }[];
}

export interface Overview {
  updated_at: string;
  kpis: { sold_out: number; in_stock: number; stale: number; pending: number };
  sold_out_by_day: { date: string; count: number }[];
  suppliers: { id: number; name: string; health: Health; last_success_at: string | null }[];
  recent_changes: {
    at: string;
    sku: string;
    from_state: VariantState;
    to_state: VariantState;
    reason: string;
  }[];
}

export interface RedStripEntry {
  supplier_id: number;
  supplier_name: string;
  last_success_at: string | null;
}

export interface Banner {
  red_strip: RedStripEntry[];
  counts: { approvals: number; orders: number; notifications: number };
}

export interface Settings {
  shopify: { shop_domain: string; client_id: string; has_client_secret: boolean };
  mailbox: { host: string; user: string; has_password: boolean };
  kill_switch: { percent: number; max_flips: number };
  sold_out_window_h: number;
  order_poll_min: number;
}
export type SettingsUpdate = Settings & { client_secret?: string; mailbox_password?: string };

export interface TestResult {
  ok: boolean;
  detail: string;
}

export interface Me {
  username: string;
}
export interface LoginBody {
  username: string;
  password: string;
  totp: string;
}

/** The flow definition JSON (PLAN.md section 11). Screens that edit it narrow this type. */
export type FlowDefinition = Record<string, unknown>;

/** One step of a Test run (docs/api.md, Test runs). */
export interface TestRunStep {
  node_id: string;
  type: string;
  ok: boolean;
  error: string | null;
  screenshot_url: string | null;
  at: string;
}
export interface TestRunSnapshot {
  screenshot_url: string;
  html_url: string;
}
export interface TestRunReading {
  result: "in_stock" | "out_of_stock" | "listing_removed" | "unknown";
  error_kind: string | null;
  quantity: number | null;
  matched_rule: string | null;
}
export interface TestRun {
  id: number;
  state: "queued" | "running" | "waiting_for_code" | "done" | "failed";
  mode: "login" | "extract";
  steps: TestRunStep[];
  snapshot: TestRunSnapshot | null;
  reading: TestRunReading | null;
  login_result: string | null;
  error: string | null;
  /** Always false: Test runs never write to Shopify. */
  wrote_to_shopify: false;
}
export interface NewTestRun {
  supplier_id: number;
  /** An unsaved draft; omitted means the saved flow. */
  flow?: FlowDefinition;
  mode: "login" | "extract";
  /** Stop after this node and return a snapshot of the page there (the selector picker). */
  up_to_node_id?: string;
  /** Required for mode "extract". */
  listing_url?: string;
}
