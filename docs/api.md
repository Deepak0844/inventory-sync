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
- `GET|PUT /api/suppliers/{id}/flow`: the flow definition JSON (see PLAN.md section 11). `PUT` validates it and returns 422 with the validator messages.
- `POST /api/suppliers/{id}/login` (the Login button) -> 202, queues a login run. `POST /api/suppliers/{id}/retry` clears a pause. `POST /api/suppliers/{id}/check` queues a check now.
- `GET /api/suppliers/{id}/runs` -> `{items: [{id, kind, state, started_at, finished_at, summary}]}`.

## Login Code prompt (global card)
- `GET /api/login-code/pending` -> `[{supplier_id, supplier_name, expires_at}]`. The dashboard polls it every few seconds.
- `POST /api/suppliers/{id}/login-code` `{code}` -> 202. 404 when that Supplier is not waiting.

## Listings, mappings, variants (screens 4, 5)
- `GET /api/listings?supplier_id=&q=&status=&cursor=&limit=` -> `{items: [{id, supplier_id, url, selection_hint, status, quantity, removed, last_success_at}], total, next_cursor}`.
- `POST /api/listings/import` multipart `file` (CSV with header `sku,supplier,url[,selection_hint]`, `supplier` is the Supplier name) -> `{created, updated, errors: [{row, message}]}`. Valid rows are applied even when others fail.
- `GET /api/variants?state=&stale=&q=&cursor=&limit=` -> `{items: [{id, shopify_variant_id, sku, title, state: "available"|"sold_out"|null, sold_out_at, stale, listings: [{listing_id, supplier_id, priority}], readings: [{result, read_at}]}], total, next_cursor}`. `readings` are the last 12, newest last (the reading strip).
- `GET|PUT /api/variants/{id}/mappings` `[{listing_id, priority}]`. `PUT` replaces.

## Approvals (screen 6)
- `GET /api/approvals` -> `[{id, supplier_id, supplier_name, created_at, changes: [{variant_id, sku, from_state, to_state}]}]`.
- `POST /api/approvals/{id}/approve` applies the held changes to Shopify (202). `POST /api/approvals/{id}/reject` discards them.

## Notifications (screen 7)
`Notification`: `{id, kind, supplier_id, supplier_name, message, created_at, resolved_at, screenshot_url}`. `kind` is one of `login_attention`, `needs_code`, `flow_failure`, `pending_approval`, `supplier_unreachable`, `blocked`, `listing_removed`, `stale_variants`, `shopify_error`, `daily_summary`.
- `GET /api/notifications?resolved=false` -> `Notification[]`. `POST /api/notifications/{id}/resolve` -> 204.

## Orders (screen 10)
- `GET /api/orders/flagged` -> `[{order_id, name, created_at, reasons: ("stale"|"recently_sold_out"|"lines_truncated")[], variants: [{sku, reason}]}]`.

## Overview and banner (screen 1, shell)
- `GET /api/overview` -> `{updated_at, kpis: {sold_out, in_stock, stale, pending}, sold_out_by_day: [{date, count}], suppliers: [{id, name, health, last_success_at}], recent_changes: [{at, sku, from_state, to_state, reason}]}`.
- `GET /api/banner` -> `{red_strip: [{supplier_id, supplier_name, last_success_at}], counts: {approvals, orders, notifications}}`. Polled by the shell.

## Settings (screen 11)
- `GET|PUT /api/settings` -> `{shopify: {shop_domain, client_id, has_client_secret}, mailbox: {host, user, has_password}, kill_switch: {percent, max_flips}, sold_out_window_h, order_poll_min}`. Secrets are accepted on `PUT` as `client_secret` and `mailbox_password` and never returned.
- `POST /api/settings/shopify/test` -> `{ok, detail}` checks the credentials without writing inventory.

## Health
- `GET /health` -> `{status, database}` (no auth).
