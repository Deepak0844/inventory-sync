import { flowErrors } from "../suppliers/flowErrors";

const START_FALLBACK = "Couldn't start the test run. Try again.";

const STEPS: Record<string, string> = {
  goto: "Go to URL",
  fill: "Fill",
  click: "Click",
  wait_for: "Wait for",
  await_code: "Wait for a code",
  branch: "Branch",
  save_session: "Save session",
};
const STATES: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  waiting_for_code: "Waiting for a code",
  done: "Done",
  failed: "Failed",
};
const READINGS: Record<string, string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  listing_removed: "Listing removed",
  unknown: "Unknown",
};
const ERROR_KINDS: Record<string, string> = {
  flow_failure: "The stock element wasn't found on the page.",
  session_lost: "The Supplier asked for a login, so the saved session was lost.",
  blocked: "The Supplier showed a block or CAPTCHA page.",
  no_rule_matched: "The stock text matched neither the in-stock rule nor the out-of-stock rule.",
  browser_error: "The browser couldn't load the page in time.",
};
const LOGIN_RESULTS: Record<string, string> = {
  logged_in: "Logged in",
  session_reused: "Reused the saved session",
  wrong_code: "The Supplier refused the code",
  bad_credentials: "The Supplier refused the username or password",
  code_timeout: "No code arrived in time",
  blocked: "The Supplier showed a block or CAPTCHA page",
  browser_error: "The browser couldn't load the page in time",
  flow_failure: "A step in the flow didn't find its element",
};

/** Words for what the worker reported. A value this build does not know is shown as it is. */
export const stepName = (type: string): string => STEPS[type] ?? type;
export const stateText = (state: string): string => STATES[state] ?? state;
export const readingText = (result: string): string => READINGS[result] ?? result;
export const errorKindText = (kind: string): string => ERROR_KINDS[kind] ?? kind;
export const loginResultText = (result: string): string => LOGIN_RESULTS[result] ?? result;

/** Messages for a Test run that could not start: the draft's validation errors, or a plain sentence. */
export function startErrors(error: unknown): string[] {
  const detail = (error as { data?: { detail?: unknown } } | undefined)?.data?.detail;
  const usable = typeof detail === "string" || (Array.isArray(detail) && detail.length > 0);
  return usable ? flowErrors(error) : [START_FALLBACK];
}
