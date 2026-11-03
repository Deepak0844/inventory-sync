# Inventory Sync

Keeps a dropshipping Shopify store honest about availability. It watches each Supplier's site and sets a Variant's Shopify inventory to 0 when every Listing for it is Out of Stock, then restores it when one comes back. Words like Supplier, Listing, Variant and Stock Status are defined in [GLOSSARY.md](GLOSSARY.md).

- [PLAN.md](PLAN.md): decisions, flows and build phases
- [docs/api.md](docs/api.md): the dashboard API
- [docs/flow-nodes.md](docs/flow-nodes.md): every flow node type, with an example
- [docs/DESIGN.md](docs/DESIGN.md): the dashboard's look
- [docs/adr/](docs/adr/): decisions that would surprise a reader

## What it does

- **Reads** Listings on a schedule with Playwright, logging in (password plus a Login Code) only when the saved session has expired. The code is pasted in the dashboard or read from a dedicated mailbox, whichever arrives first.
- **Decides** with pure functions in `backend/app/engine/`. Out of Stock needs two readings about 30 minutes apart, In Stock needs one, and an Unknown reading never changes Shopify.
- **Protects** the store: if 30% or more of a Supplier's Listings (or more than 20) flip to Out of Stock in one run, the changes wait as Pending Approval. Orders containing a Stale or recently Sold Out Variant are flagged "verify with Supplier". A Supplier is paused after a wrong password or two wrong codes.
- **Shows** it all in a dashboard (Suppliers, Listings and CSV import, Variants, approvals, notifications, orders to verify, settings).
- **Builds flows visually.** The flow builder has a palette of steps, a selector picker that works on a snapshot of the real page, and Test runs that show each step with masked screenshots. Test runs never write to Shopify.

Not built yet: deployment (VPS, Caddy, backups), the `code` flow node, and Suppliers that offer a feed instead of a site.

## Run it locally

You need Docker and Node 22.

```bash
cp .env.example .env
# set POSTGRES_PASSWORD (letters, digits, - _ only) and ENCRYPTION_KEY:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up -d --build        # Postgres, API (runs migrations) and worker
docker compose exec api python -m app.cli create-admin   # asks for a password, prints the 2FA secret once

cd frontend && npm ci && npm run dev    # http://localhost:5173
```

Add the printed secret to an authenticator app, then sign in with your username, password and the 6-digit code. The API is on `http://127.0.0.1:8000` (`/health` needs no sign-in).

Shopify and mailbox credentials are entered under Settings in the dashboard. The Shopify app needs the scopes `read_products`, `read_inventory`, `write_inventory` and `read_orders`. Use a development store until a real Supplier is approved.

### Manual login (for a Supplier that shows a CAPTCHA)

Some Suppliers show a CAPTCHA that an automated login cannot pass. The optional private browser lets you complete that login yourself. This does not solve or bypass the CAPTCHA: you do it, in an ordinary Chromium that nothing is controlling (a browser driven by Playwright reports itself as automated, and a CAPTCHA can then reject a correct answer; see [ADR 0003](docs/adr/0003-manual-login-uses-a-plain-browser.md)). The worker then reuses your session headless.

Set these values in `.env`, using a strong dedicated VNC password:

```dotenv
MANUAL_BROWSER_ENABLED=true
MANUAL_BROWSER_PASSWORD=change-this-password
```

Start the profile. On a VPS, open an SSH tunnel from your laptop (locally you can skip the tunnel):

```bash
docker compose --profile manual-login up -d --build
ssh -N -L 6080:127.0.0.1:6080 your-user@your-vps
```

Port 6080 is bound to loopback by Compose. Do not publish it on `0.0.0.0`, and do not put noVNC behind the public Caddy site. The steps for using it are under [Workflow 1](#workflow-1-logging-in-to-a-supplier).

## Add a Supplier, step by step

Build the login before the stock check, because for most Suppliers stock is only visible after logging in.

1. **Add the Supplier** in the dashboard: name, site URL and check interval.
2. **Enter the username and password.** They are stored encrypted and never shown again.
3. **Choose the Login Code methods:** pasted in the dashboard, read from the mailbox, or none.
4. **Build the login flow** in the Supplier's Flow tab: the steps that open the login page and sign in, the **Signed-in page address** (a page only a signed-in user can see) and the **logged-in marker** (an element on that page).
5. **Log in.** Use **Log in** for a normal login, or **Manual login** for a Supplier with a CAPTCHA (see below).
6. **Build the stock check** on one real product page (see [Workflow 2](#workflow-2-checking-a-listings-stock)) and run a Test run in extract mode.
7. **Test 3 to 5 sample Listings** and compare each reading with the Supplier's site.
8. **Import Listings by CSV** and map each Variant to its Listings.
9. **Activate.** The scheduler starts checking on the interval.

## Workflow 1: Logging in to a Supplier

The worker logs in only when it has no working session, so most checks never log in and never need a code.

**Every check starts like this:**
1. Load the Supplier's saved session (encrypted cookies), if there is one.
2. Open the flow's Signed-in page address and look for the logged-in marker.
3. If the marker is there, the session works and the check goes on to read Listings.
4. If not, the session is dropped and the login flow runs.

**The automated login flow:**
1. Open the login page, fill the username and password (masked in screenshots and logs) and click Log in.
2. If the Supplier asks for a Login Code, the dashboard shows a **needs code** prompt. Paste the code, or let the mailbox deliver it. When both are on, the first to arrive wins. The prompt stays open for 10 minutes (editable per Supplier).
3. Fill the code, then wait for the logged-in marker.
4. Save the session. Ticking "trust this device" in the flow makes it last longer. The dashboard shows each session's age.

**When the login goes wrong:**
- A wrong password pauses the Supplier at once, because retrying risks locking the account.
- A wrong code allows one retry, then pauses the Supplier. Use **Retry login** to clear the pause.
- No code before the prompt expires cancels the run and shows "Needs code". That is not a failed attempt.
- A CAPTCHA or block marks the Supplier **Blocked**. Its readings are Unknown, so nothing changes in Shopify.

**Manual login, for a Supplier with a CAPTCHA:**
1. Make sure the flow has the Signed-in page address and the logged-in marker. A draft flow is enough.
2. In the Supplier's **Login and 2FA** tab, click **Manual login**, then **Open private browser**.
3. Enter `MANUAL_BROWSER_PASSWORD` when noVNC asks.
4. In the browser, sign in and solve the CAPTCHA and any code yourself.
5. Back in the dashboard, click **Done, I'm logged in**. Closing the browser window also counts as Done.
6. The tab shows **Checking your login…** while the worker closes the browser, reads its cookies, opens the Signed-in page headless and looks for the marker.
7. On success the session is saved encrypted, a login pause or block is cleared, and scheduled checks reuse the session. On failure the earlier session is kept and the tab shows why.

The manual session ends after 10 minutes. **Cancel manual login** closes it sooner. Only the Supplier's own cookies are saved, not local storage. A CAPTCHA may still appear later, because the Supplier controls its own risk checks. If a Supplier keeps rejecting even a plain browser, it does not want this login automated: ask for a feed or written permission.

## Workflow 2: Checking a Listing's stock

This is the scraping step. Each check reads every Listing of the Supplier, decides what changed and updates Shopify only when it is safe.

**Reading one Listing (the stock check):**
1. Open the Listing URL with the logged-in session.
2. Look at the response:
   - A 404, or a redirect to a category page, is **Listing Removed**.
   - A login page means the session was lost: the reading is Unknown and the login runs once more.
   - A CAPTCHA or block is Unknown (blocked).
3. If the Mapping has a selection hint (for example size L), choose that option first.
4. Wait for the stock element. If it never appears, the reading is Unknown (flow failure) with a masked screenshot.
5. Read the text, badge, quantity or button state and apply the rules:
   - It matches the in-stock text: **In Stock**, with the quantity if the page shows one.
   - It matches the out-of-stock text: **Out of Stock**.
   - It matches neither: Unknown.

**Deciding (pure functions in `backend/app/engine/`):**
1. A Listing becomes **In Stock** after 1 In Stock reading.
2. It becomes **Out of Stock** only after 2 Out of Stock readings in a row, about 30 minutes apart. The worker queues the second reading itself.
3. An **Unknown** reading never changes anything.
4. A Variant is **Sold Out** when every Listing mapped to it is Out of Stock. Shopify inventory is set to 0.
5. When any Listing is In Stock again, the Variant is **Restored** with a default quantity.

**The safety layer:**
- If 30% or more of a Supplier's Listings (or more than 20) flip to Out of Stock in one run, the changes wait as **Pending Approval** until you decide.
- A Variant that is **Stale** (Unknown, or last checked longer than twice its interval ago) flags any order containing it as "verify with Supplier".
- A paused Supplier is skipped and keeps its status. A Blocked one is still checked, and its readings stay Unknown while the block lasts.

**Picking the stock element:**
1. Finish a login first, so the Test run has a session.
2. In the Flow tab, run a Test run in extract mode with one real product page URL.
3. Click the stock text, badge or quantity in the snapshot. The picker chooses a stable selector.
4. Set the text that means In Stock and the text that means Out of Stock.
5. Save the flow. If the page needs a click or hover before it shows stock, add that step first.

Test runs never write to Shopify and never save cookies back.

## Configuration

Set these in `.env` (see `.env.example`):

| Variable | Required | What it does |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Database password. Letters, digits, `-` and `_` only, because it is placed inside `DATABASE_URL`. |
| `ENCRYPTION_KEY` | yes | Fernet key that encrypts Supplier passwords, sessions and settings. Losing or changing it makes saved credentials unreadable. |
| `MANUAL_BROWSER_ENABLED` | no | `true` shows the Manual login control in the dashboard. |
| `MANUAL_BROWSER_PASSWORD` | with the above | The password noVNC asks for when you open the private browser. |
| `MANUAL_BROWSER_URL` | no | Where the dashboard's "Open private browser" link points. Defaults to the local noVNC page on port 6080. |
| `DATA_DIR` | no | Where Test run screenshots are kept. The compose file mounts a shared volume at `/srv/data`. |

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| "Not logged in: the account page did not show you as signed in… Opened *URL* with *N* cookies" | The check opened that page and did not find the logged-in marker. | If the URL is not your real account page, fix **Signed-in page address** in the Flow tab. With 0 or 1 cookies, the login did not stick, so log in again and press Done after the page loads. With many cookies and the right page, check the marker selector. |
| "no flow or credentials" on a check | The Supplier has only a draft flow, or no username and password. | Save the flow, and save the credentials in the Login tab. |
| Supplier shows **Blocked** | The Supplier showed a CAPTCHA or blocked the worker. | Use Manual login. If it is still rejected, ask the Supplier for a feed. |
| Supplier shows **Needs code** | A login asked for a code and none arrived in 10 minutes. | Click **Log in** and paste the code when the prompt appears. |
| Supplier is paused for a wrong password or code | The worker stopped to avoid locking the account. | Fix the credentials, then click **Retry login**. |
| No **Manual login** control | The private browser is off. | Set `MANUAL_BROWSER_ENABLED=true` and start the `manual-login` profile. |
| Many Listings turn Unknown | The stock element or text no longer matches the page. | Run a Test run in extract mode on a Listing and re-pick the element. |

## Develop

```bash
cd backend
uv sync
docker run -d --rm -p 55433:5432 -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t postgres:16
export TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55433/t
uv run playwright install chromium
uv run ruff check . && uv run mypy --strict app tests mock_supplier && uv run pytest -q

cd ../frontend
npm run lint && npm run typecheck && npm test -- --run && npm run build
```

The database tests fail on purpose when `TEST_DATABASE_URL` is unset. Tests use the mock Supplier in `backend/mock_supplier/` and never a real shop. CI runs both suites on every pull request.

```
backend/app/
  api/ services/   routes, then business logic
  engine/          decision engine, kill switch, Stale and order flags (pure)
  flows/           JSON flow definition, node types, runner
  worker/ scheduler/  jobs and the schedule
  db/              models, repositories, Postgres job queue
  shopify/ mail/   Admin API client, IMAP reader
  core/            config, encryption, secret masking
backend/mock_supplier/   local test Supplier
frontend/src/            screens, features, API slice, design tokens
```
