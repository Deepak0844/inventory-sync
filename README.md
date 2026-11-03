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
