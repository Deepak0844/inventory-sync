# Flow node types

A Supplier's flow is JSON (see PLAN.md section 11). `nodes` run in the order the `edges` lead; an edge is `["from", "to"]`, or `["from", "to", "yes"]` / `["from", "to", "no"]` leaving a `branch`. The flow is checked when it is loaded: unique ids, edges that point at real nodes, one start node, no cycles, and a `wait_for` with role `logged_in_marker` on every path, at least one `save_session`, `email` settings on any `await_code` that lists `email_code`, and labels only on `branch` edges.

Templates are only supported in `fill` (not in `goto`, `click` and so on). In a `fill` value you can use `{{credentials.username}}`, `{{credentials.password}}` and `{{code}}`. Any other name is rejected on load.

After every node the runner checks the page for the `blocked_if` text (for example a CAPTCHA) and stops with Blocked.

## goto
Open a URL.
```json
{ "id": "n1", "type": "goto", "url": "https://supplier-a.example/login" }
```

## fill
Type into a field. `mask: true` marks the field to be masked in Test run screenshots (Phase 6). The runner itself never logs values.
```json
{ "id": "n3", "type": "fill", "selector": "#password", "value": "{{credentials.password}}", "mask": true }
```

## click
Click an element. The time of the click is remembered, and a mailbox Login Code is only accepted if it arrived after it.
```json
{ "id": "n4", "type": "click", "selector": "button[type=submit]" }
```

## wait_for
Wait until an element is visible (`timeout_s`, default 5). The `role` says what a timeout means:
- `code_prompt`: the code box never appeared, so the login is reported as bad credentials.
- `logged_in_marker`: signed-in element. A timeout is a wrong code, or bad credentials if no code was entered. Session reuse also uses this selector.
- no role: a plain flow failure.

A missing `code_prompt` counts as bad credentials, so a Supplier that sometimes skips 2FA needs a `branch` on the code box (`if_visible` the code field): `yes` goes through `await_code`, `no` goes straight to the `logged_in_marker` wait.
```json
{ "id": "n8", "type": "wait_for", "selector": ".account-menu", "role": "logged_in_marker", "timeout_s": 5 }
```

## await_code
Wait for a Login Code. `methods` lists where to look and the first code to arrive wins. `email` is needed for `email_code`. If nothing arrives within `timeout_s` the run is cancelled and no failed attempt is counted.
```json
{ "id": "n5", "type": "await_code", "methods": ["ui_code", "email_code"],
  "email": { "sender": "no-reply@supplier-a.example", "pattern": "\\b(\\d{6})\\b" }, "timeout_s": 600 }
```

## branch
Follow the `yes` edge if the element is visible, otherwise the `no` edge. Both edges are required.
```json
{ "id": "b1", "type": "branch", "if_visible": "#cookie-banner" }
```
with edges `["b1", "dismiss", "yes"]` and `["b1", "next", "no"]`.

## save_session
Save the browser cookies, encrypted, for the next run.
```json
{ "id": "n9", "type": "save_session" }
```

## extract (the `extract` section)
Not a node: it is read after login for each Listing. Text matching is case-insensitive. Out-of-stock is checked first. Anything that matches neither rule is Unknown.
```json
"extract": {
  "stock_selector": ".stock-status",
  "in_stock_if": { "contains": "In stock" },
  "out_of_stock_if": { "contains": "Out of stock" },
  "quantity_selector": ".qty-left"
}
```

## Not built yet
The `code` node for odd sites runs arbitrary code, so it needs a sandbox decision first. It is left out until a real Supplier needs it.
