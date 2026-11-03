# Dashboard API contract

JSON over HTTP under `/api`, shared by the FastAPI backend and the RTK Query slice in the dashboard. Times are ISO 8601 UTC strings. Ids are integers unless stated. Secrets (Supplier password, Shopify secret, mailbox password) are write-only: responses say `has_password: true`, never the value. Every route except `/health` and `POST /api/auth/login` needs the session cookie. Errors are `{ "detail": "..." }` (or FastAPI's 422 list). The vocabulary is [GLOSSARY.md](../GLOSSARY.md).

## Auth (screen 12)
- `POST /api/auth/login` `{username, password, totp}` -> 204 and an httponly SameSite=Strict `session` cookie. Wrong anything -> 401 `{detail: "Sign in failed"}` (never says which part). 5 failures per username per 15 minutes -> 429.
- `GET /api/auth/me` -> `{username}`. `POST /api/auth/logout` -> 204.
- The single admin is created with `python -m app.cli create-admin` (prints the TOTP secret and otpauth URI once).

## Suppliers (screens 2, 3)
`Supplier`: `{id, name, site_url, stock_source: "scrape"|"feed", interval_min, out_confirm_reads, in_confirm_reads, confirm_gap_min, removed_as_unknown, max_quantity, two_fa_methods: ("ui_code"|"email_code")[], code_window_min, paused, pause_reason, health: "healthy"|"needs_code"|"paused"|"stale"|"blocked", last_success_at, session_age_s, listing_count}`.
- `GET /api/suppliers`, `POST /api/suppliers` (name, site_url, interval_min required), `GET|PATCH|DELETE /api/suppliers/{id}`.
- `PUT /api/suppliers/{id}/credentials` `{username, password}` -> 204. `GET` -> `{username, has_password}`.
- `GET|PUT /api/suppliers/{id}/flow`: the flow definition JSON (see PLAN.md section 11). `GET` answers `null` (200) when the Supplier has no flow yet, and 404 only for an unknown Supplier. `PUT` validates it and returns 422 with the validator messages.
- `POST /api/suppliers/{id}/login` (the Login button) -> 202, queues a login run. `POST /api/suppliers/{id}/retry` clears a pause. `POST /api/suppliers/{id}/check` queues a check now.
- `GET /api/suppliers/{id}/runs` -> `{items: [{id, kind, state, started_at, finished_at, summary}]}`.

## Login Code prompt (global card)
- `GET /api/login-code/pending` -> `[{supplier_id, supplier_name, expires_at}]`. The dashboard polls it every few seconds.
- `POST /api/suppliers/{id}/login-code` `{code}` -> 202. 404 when that Supplier is unknown or has no open code prompt; 422 for a blank code.

## Test runs (flow builder, screens 8 and 9)
A Test run executes a flow in the worker's browser and reports each step. **It never writes to Shopify and never changes a Listing's Stock Status** (`wrote_to_shopify` is always `false`). Passwords and Login Codes are masked in every screenshot.

When the private manual-browser profile is enabled, a human can establish a reusable session for a Supplier whose site presents a CAPTCHA:

- `POST /api/suppliers/{id}/manual-login` queues a 10-minute visible-browser session. It is idempotent while one is queued or running.
- `GET /api/suppliers/{id}/manual-login` returns `{enabled, session}`. `session` is null or the latest attempt (states below).
- `POST /api/suppliers/{id}/manual-login/finish` is the **Done** button: it asks the worker to close the browser, check the login and save the session. 202 when the session is `ready`, 409 when it is not (not started, still starting, or already finished), 404 for an unknown Supplier, 503 when the private browser is not enabled.
- `DELETE /api/suppliers/{id}/manual-login` cancels an open session.

States, in order: `queued` (waiting for the worker), `ready` (the browser is open), `finishing` (Done was pressed), `verifying` (the worker is checking the login), then `succeeded`, `failed` (with `error`), `expired` or `cancelled`. The browser is an ordinary Chromium, so the worker only learns the result after Done. A check that finds no logged-in marker ends as `failed` and keeps the Supplier's earlier session.

The response includes the loopback noVNC URL. Access is intended through an SSH tunnel; the VNC password is never returned by the API.
- `POST /api/test-runs` `{supplier_id, flow?, mode: "login"|"extract", up_to_node_id?, listing_url?}` -> 202 `{id}`. `flow` is an unsaved draft (the saved flow when omitted) and is validated first (422 with the validator messages). A draft may leave the Stock element empty, because the owner needs a snapshot to pick it from (saving the flow still requires it, and `mode: "extract"` needs it). Supplier credentials are only required when a step that will run types them: a snapshot of the login page needs none, and neither does a run that stops before the first `{{credentials.*}}` fill. `mode: "login"` runs the login nodes (it reuses the Supplier's saved session when valid; `up_to_node_id` stops after that node and returns a snapshot of the page there). `mode: "extract"` logs in if needed, opens `listing_url` and applies the extract rules. A login that needs a Login Code sets the state to `waiting_for_code` and uses the global "needs code" prompt. The request is validated first (404 unknown Supplier, 422 for any problem), then **409** `{detail: "A test run is already in progress for this Supplier.", run_id}` if the Supplier has a run that is still `queued`, `running` or `waiting_for_code`; the builder should show that run instead of starting another. A run still open after 30 minutes belongs to a worker that died: the worker marks it `failed` (`error: "The test run did not finish."`) and it no longer blocks a new one. The state goes back to `running` as soon as the Login Code is taken.
- `GET /api/test-runs/{id}` -> `{id, state: "queued"|"running"|"waiting_for_code"|"done"|"failed", mode, steps: [{node_id, type, ok, error, screenshot_url, at}], snapshot: {screenshot_url, html_url} | null, reading: {result, error_kind, quantity, matched_rule} | null, login_result, error, wrote_to_shopify: false}`. Polled while `queued`, `running` or `waiting_for_code`. `login_result` is a login outcome (`logged_in`, `session_reused`, `wrong_code`, `bad_credentials`, `code_timeout`, `blocked`, `browser_error`, `flow_failure`), or `stopped_after_node` when `up_to_node_id` ended the run early. If `up_to_node_id` names a node the path taken never reaches (for example the other side of a branch), the run is `failed` with `login_result: "flow_failure"`, `error: "That step was not reached on this path (check the branch)."` and no snapshot. A login that fails ends the run as `failed` with `error` set. A Test run never counts toward a Supplier's failed attempts and never pauses it, and it works on a copy of the saved session (it never saves cookies back).
- `GET /api/test-runs/{id}/files/{name}` serves a screenshot (PNG) or the snapshot HTML. `html_url` returns a cleaned copy of the page for the selector picker: scripts, event handlers, iframes, `<textarea>`, `<meta>`, `<noscript>` and external resources removed, every `<input type="hidden">` removed, every input value blanked (so passwords and codes are never in it), and every `data-*` attribute dropped except `data-testid`, `data-test` and `data-cy`. The page's visible text is kept.

## Listings, mappings, variants (screens 4, 5)
- `GET /api/listings?supplier_id=&q=&status=&cursor=&limit=` -> `{items: [{id, supplier_id, url, selection_hint, status, quantity, removed, last_success_at}], total, next_cursor}`.
- `POST /api/listings/import` multipart `file` (CSV with header `sku,supplier,url[,selection_hint]`, `supplier` is the Supplier name) -> `{created, updated, errors: [{row, message}]}`. Valid rows are applied even when others fail.
- `GET /api/variants?state=&stale=&q=&cursor=&limit=` -> `{items: [{id, shopify_variant_id, sku, title, state: "available"|"sold_out"|null, sold_out_at, stale, listings: [{listing_id, supplier_id, priority}], readings: [{result, read_at}]}], total, next_cursor}`. `readings` are the last 12, newest last (the reading strip). `stale` uses the shortest check interval among the Variant's Suppliers.
- `GET|PUT /api/variants/{id}/mappings` `[{listing_id, priority}]`. `PUT` replaces.

## Approvals (screen 6)
- `GET /api/approvals` -> `[{id, supplier_id, supplier_name, created_at, changes: [{variant_id, sku, from_state, to_state}]}]`.
- `POST /api/approvals/{id}/approve` queues the held changes for the worker to apply (202). `POST /api/approvals/{id}/reject` discards them (204). Both are 404 for an unknown or already decided id, so a double click never applies twice.

## Notifications (screen 7)
`Notification`: `{id, kind, supplier_id, supplier_name, message, created_at, resolved_at, screenshot_url}`. `kind` is one of `login_attention`, `needs_code`, `flow_failure`, `pending_approval`, `supplier_unreachable`, `blocked`, `listing_removed`, `stale_variants`, `shopify_error`, `daily_summary`.
- `GET /api/notifications?resolved=false` -> `Notification[]`. `POST /api/notifications/{id}/resolve` -> 204.
- `GET /api/notifications/{id}/screenshot` serves the masked failure screenshot (`screenshot_url` points here). It only serves files inside the server's screenshot folder; anything else is 404.

## Orders (screen 10)
- `GET /api/orders/flagged` -> `[{order_id, name, created_at, reasons: ("stale"|"recently_sold_out"|"lines_truncated")[], variants: [{sku, reason}]}]`.

## Overview and banner (screen 1, shell)
- `GET /api/overview` -> `{updated_at, kpis: {sold_out, in_stock, stale, pending}, sold_out_by_day: [{date, count}], suppliers: [{id, name, health, last_success_at}], recent_changes: [{at, sku, from_state, to_state, reason}]}`.
- `GET /api/banner` -> `{red_strip: [{supplier_id, supplier_name, last_success_at}], counts: {approvals, orders, notifications}}`. Polled by the shell. A Supplier never checked is not in the red strip (it has no last success to be old); it shows as `stale` in the Suppliers list.

## Settings (screen 11)
- `GET|PUT /api/settings` -> `{shopify: {shop_domain, client_id, has_client_secret}, mailbox: {host, user, has_password}, kill_switch: {percent, max_flips}, sold_out_window_h, order_poll_min}`. Secrets are accepted on `PUT` as `client_secret` and `mailbox_password` and never returned.
- `POST /api/settings/shopify/test` -> `{ok, detail}` checks the credentials without writing inventory. It always answers 200; a failure is `ok: false` with a message that never contains the secret.

## Health
- `GET /health` -> `{status, database}` (no auth).
