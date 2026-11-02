# Dashboard design

The dashboard's look, screens and design tokens. Decisions and flows are in [PLAN.md](../PLAN.md); vocabulary is in [GLOSSARY.md](../GLOSSARY.md). Two other styles were compared and not chosen: Achromatic ledger and Accent ladder.

## Decisions

- **Style: Framed sheet.** One tinted frame holds the sidebar and a 48px top bar with no rule between them. The page is a white sheet inset 8px from the window's right and bottom edges, with a 1px edge, 16px corners and no shadow.
- **Light theme only** for the first version. Components use tokens only, so a dark theme can be added later without rewriting them.
- **Tailwind**, mapped to the design tokens below. No component hard-codes a colour, size or radius.
- **Type:** IBM Plex Sans. IBM Plex Mono for IDs and keys only.
- **Server data:** RTK Query (see the stack in PLAN.md).

## The look

- The chrome is grey and ink. Colour appears on data and on status, and nowhere else. The brand shrinks to the product mark and a 2px underline on the active tab.
- Surfaces are separated by a 1px border or one tone step. A border or a shadow, never both. Nothing at rest has a shadow.
- Three nesting levels at most: frame, sheet, card.
- Status colour is for what needs attention. Sold Out and errors get a pale red pill. Needs code, Stale and Pending get a pale amber pill. A Restore gets a pale green pill. Variants that are In Stock and Suppliers that are healthy stay grey and carry no pill.
- Colour says good or bad, not up or down. A rise in Sold Out variants is bad, so it is marked as bad.
- Text in three tiers (ink, secondary, tertiary), every tier at 4.5:1 or better on the surface it sits on.
- Banned: gradients, glows, glass, icons in tinted squares, sparklines on KPIs, rainbow charts, emoji, lorem ipsum, and invented vanity numbers.

### Tokens

Three layers, as in the design-system skill. Primitive values map to semantic purposes, which map to component tokens. Components only use the semantic and component layers.

```css
:root {
  /* primitive */
  --grey-50: #f9fbfc;  --grey-100: #f4f6f8;  --grey-200: #ebedee;  --grey-300: #e8eaec;
  --ink-900: #131416;  --grey-600: #5d5f60;  --teal-700: #1b6c80;  --blue-600: #2f70bb;
  --red-600: #c4242a;  --amber-800: #92400e;  --green-700: #1e7b4f;

  /* semantic */
  --ground: var(--grey-50);       /* the frame: sidebar and top bar */
  --surface: #ffffff;             /* the sheet and cards */
  --raised: var(--grey-100);
  --active: var(--grey-200);      /* active nav pill, selected row */
  --border: var(--grey-300);
  --rule: #f0f1f2;
  --control: #cdced1;
  --text: var(--ink-900);
  --muted: var(--grey-600);
  --accent: var(--teal-700);
  --chart-1: var(--teal-700);     /* the main data element */
  --chart-2: var(--blue-600);
  --chart-3: #a86f0c;
  --positive: var(--green-700);
  --negative: var(--red-600);
  --warning: var(--amber-800);

  /* component */
  --pill-positive-bg: #dcfae5; --pill-positive-ink: #04250e;
  --pill-negative-bg: #ffedea; --pill-negative-ink: #831c1e;
  --pill-warning-bg:  #fffbeb; --pill-warning-ink:  #92400e;
  --pill-neutral-bg:  #ebedee; --pill-neutral-ink:  #353736;

  --radius-card: 8px;  --radius-control: 6px;  --radius-sheet: 16px;  --sheet-inset: 8px;
  --row-height: 48px;  --sidebar-width: 228px;  --topbar-height: 48px;
  --gap: 24px;  --pad: 24px;  --control-height: 32px;
  --fs-title: 22px;  --fs-section: 16px;  --fs-kpi: 28px;  --fs-body: 14px;  --fs-small: 12px;
}
```

The Tailwind theme reads these variables, so `bg-surface`, `text-muted` and `rounded-card` resolve to the tokens.

### Type

- IBM Plex Sans at weights 400, 500 and 600. Sizes: title 22, section 16, KPI 28, body 14, small 12.
- KPI values at weight 400. The semibold goes on labels and the active tab.
- Tabular figures on every table, KPI and anything that updates. Numbers are right-aligned with fixed decimals.
- Sentence case everywhere. No tracked capitals.

## Shell

- The sidebar sits on the frame, 228px wide, with the product mark and name at the top and a scope switcher under it (the store).
- Nav rows are 32px on a 34px pitch, with 16px outline icons. The active item is a neutral grey pill.
- A count appears only on a queue that needs action, with a clear noun: Approvals 2, Orders to verify 4.
- The top bar is 48px with search in the middle and a freshness stamp ("Updated 14:02") on the right.
- The red strip: when a Supplier's last successful check is older than twice its interval, a thin red strip appears across the top of every screen naming it. When nothing is wrong, nothing extra is shown.
- The "needs code" prompt is a card at the top of every screen, shown only while a Supplier is waiting. It holds the input, a countdown and the Supplier's name.

## Screens

There are 12, plus the global prompt. Each answers one question.

| # | Screen | The one question it answers |
|---|---|---|
| 1 | Overview | "Is my stock trustworthy right now?" |
| 2 | Suppliers | "Which Suppliers are healthy?" |
| 3 | Supplier detail (tabs: Listings, Flow, Login and 2FA, Runs, Settings) | "What is wrong with this Supplier?" |
| 4 | Listings and mappings (table, CSV import) | "Which Variants are mapped, and which can't be read?" |
| 5 | Variants | "What is Sold Out, and since when?" |
| 6 | Pending approvals | "What changes are waiting for me?" |
| 7 | Notifications | "What needs fixing?" |
| 8 | Flow builder (React Flow canvas) | "Does this flow read the right thing?" |
| 9 | Test run and selector picker (panel in the builder) | "What did the worker see?" |
| 10 | Orders to verify | "Which orders may include something unavailable?" |
| 11 | Settings (Shopify, mailbox, thresholds, security) | "What are the system's rules?" |
| 12 | Sign in with 2FA | n/a |

### Overview

```
┌ frame ─────────────────────────────────────────────────────────────────┐
│ ◧ Stock Sync        [ Search suppliers, listings, variants ]  Updated  │
│ Northline Store    ┌ sheet ─────────────────────────────────────────┐ │
│                    │ Overview                                        │ │
│ ▌Overview          │ 14 variants are sold out. Supplier B needs code │ │
│  Suppliers      1  │ ┌ Supplier B needs a code ─ [______] Submit ──┐ │ │
│  Listings          │ ┌ Sold Out │ In Stock │ Stale │ Pending ──────┐ │ │
│  Variants          │ │ 14       │ 1,186    │ 3     │ 2             │ │ │
│  Approvals      2  │ ┌ Sold Out variants today (one teal line) ────┐ │ │
│  Orders         4  │ ┌ Supplier health ──┐ ┌ Recent changes ───────┐ │ │
│ Build              │                                                │ │
│  Flows             └────────────────────────────────────────────────┘ │
│ Settings                                                              │
└───────────────────────────────────────────────────────────────────────┘
```

- The biggest block is the chart, because the question is about Sold Out variants. The finding sits under the title, next to the action it drives.
- KPIs are one card split by 1px dividers, label over value. No icons and no sparklines.
- The chart is one line with straight segments, 4 gridlines, round ticks and no legend. The teal is on this main data element only.

### The element only this product has: the reading strip

Each Variant row shows its recent readings on a shared time axis: a 2px track with one tick per reading. An ink tick is In Stock, a red tick is Out of Stock, and a hollow tick is Unknown. It makes the confirmation rule visible: two red ticks in a row and the Variant becomes Sold Out. It is adapted from the skill's sell-out time strip. On a phone, the axis labels move to every two hours.

### Flow builder

- A React Flow canvas on the ground colour, a node palette on the left and a selector panel on the right.
- Nodes are plain white cards with the node type as text. Type icon tiles are allowed in a builder; the inspector needs `--allow icon-chips` with the reason recorded.
- The selector panel shows the page snapshot, where you click an element, and the Test run result with the reading and a screenshot.
- Test runs never write to Shopify, and the panel says so.
- On a phone the builder is read-only.

### Tables and lists

- Rows are 48px for one line. Headers are 12px grey sentence case with no fill and no rule.
- Numbers are right-aligned in tabular figures, a missing value is a grey dash, and a real zero is printed as 0.
- One status mark per row. One kebab at the far right.
- No zebra rows. An overview list is capped at 4–6 rows with "View all".
- A full list states its total ("1,203 variants") and loads more at the end.

### States

Each block has an empty, zero, loading and error state.
- **Empty:** the block keeps its frame and its header, with one sentence in the frame.
- **Loading:** the final layout with each value as a grey bar at its real size. No shimmer, and no layout shift.
- **Error:** inside the block that failed, never full screen. One sentence saying what failed and when the data was last good ("Couldn't load Suppliers. Last updated 09:14."), plus a Retry text button.
- **Stale or Unknown:** an honest grey dash or a Stale pill, never a guessed value.

## Phone

- The sidebar folds into a 48px top bar with the screen's name and a menu button that opens a full-screen sheet with the nav and the store switcher.
- Margins 16px, touch targets 44px, body text 14px, nothing under 12px.
- KPIs become a 2-column grid. Tables become two-line rows: the name and key figure on line 1, other fields in grey on line 2.
- Charts are full width, 160–200px tall, with 4 x labels.
- The "needs code" prompt stays at the top and is fully usable. Pasting a code is the phone's main job.

## Checks

When screens exist, run the skill's gates at 1440, 768 and 390px:

```bash
node .claude/skills/design-taste-frontend/scripts/lint.mjs --app <source>
node .claude/skills/design-taste-frontend/scripts/inspect.mjs --app <url>
```

Fix every FAIL. Look at every screenshot after the last change. Sample data must be replaced with real data before launch.
