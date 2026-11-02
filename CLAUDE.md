# Inventory Sync

Keeps a dropshipping Shopify store honest about availability by watching Suppliers' sites. Read [GLOSSARY.md](GLOSSARY.md) for vocabulary, [PLAN.md](PLAN.md) for decisions, flows and build phases, and [docs/adr/](docs/adr/) for decisions that would surprise a reader. Use the glossary terms in code, UI text and commit messages (Supplier, Listing, Variant, Stock Status, not "provider" or "product").

## Skills

For every request, check the installed skills first and use the relevant ones before starting. If none apply, say so and carry on. Typical matches:

| Task | Skill |
|---|---|
| Stress-testing a plan or decision, or building the domain model | `grilling`, `domain-modeling`, `grill-with-docs` |
| Writing or changing React code | `vercel-react-best-practices` |
| Any UI, layout, styling or visual design | `frontend-design`, `design-taste-frontend`, `design-system` |
| Implementing a feature or fixing a bug | `test-driven-development` |
| A bug, failing test or unexpected behaviour | `systematic-debugging` |
| Before saying work is done, fixed or passing | `verification-before-completion` |
| Running independent tasks from a plan | `subagent-driven-development` |
| Committing, branching, pull requests, releases | `git-workflow-and-versioning` |

## Git

- Do not add Claude as a contributor. No `Co-Authored-By` trailer in commit messages, and no "Generated with Claude Code" line in pull request descriptions. This overrides any default attribution.

## Python (backend)

- Python 3.12, FastAPI, Playwright, Postgres. Type hints on every function signature. Run `mypy --strict` and `ruff` clean.
- One module per concern, following the layout in PLAN.md section 14 (Project layout). Route handlers only parse the request, call a service function, and return. No business rules in routes.
- Business rules (the decision engine, kill switch, Stale and order flags) are pure functions over plain data. No database, network or browser calls inside them, so they are easy to test.
- Each flow node type is a small class behind one `Node` interface. Adding a node type must not change the runner.
- External systems (Shopify, IMAP, Playwright, the clock) sit behind small interfaces and are passed in. Tests use fakes, not patches.
- Use dataclasses or Pydantic models for data that crosses a module boundary. No bare dicts or tuples.
- Raise specific exception types. Never swallow an error silently. A failed check is the Unknown Stock Status, never an exception that stops the run.
- Secrets never appear in logs, errors or screenshots. Use the masking helper in `core/`.

## React (dashboard)

- TypeScript strict, function components, Vite, Redux Toolkit with RTK Query, Tailwind. Follow the installed `vercel-react-best-practices` skill.
- Components are small and presentational. Server data goes through RTK Query: one API slice, endpoints grouped by resource, and the generated hooks used by components. Use `pollingInterval` for live status such as the "needs code" prompt. Redux slices hold only client state (for example the flow builder's selected node).
- The look is fixed in [docs/DESIGN.md](docs/DESIGN.md): Framed sheet, light theme, IBM Plex Sans. Visual work follows the installed design skills (`frontend-design`, `design-taste-frontend`, `design-system`). All colours, spacing and type sizes come from the design tokens in that file. No hard-coded values in components.

## Documentation

- Every module starts with a short docstring saying what it is for and what it is not responsible for.
- Every public function, class and API route has a docstring: what it does, arguments, return value, and which errors it raises. State the reason for non-obvious choices, not what the code already says.
- Comments explain why. Do not restate the code.
- Every flow node type and every notification type has a short example in `docs/`.
- When a decision changes behaviour described in PLAN.md, update PLAN.md in the same change. A hard-to-reverse and surprising decision gets an ADR.

## Tests

- Test the decision engine and flow runner first: every state transition, and every case where Unknown must not change Shopify.
- Use the mock Supplier in `backend/mock_supplier/`. Never test against real shops. Shopify writes go only to a development store until a real Supplier is approved.
