# Design-debt ledger — 2026 experience

Every item below is real, measured debt. The adoption lint
(`web/scripts/lint-design.mjs`) is the ratchet: the counts may only go down.

Last updated: 2026-10-30.

## How to read this

| Severity | Meaning |
|---|---|
| **S1** | Breaks a 2026 acceptance gate (accessibility, trust, performance). Fix before the next pilot. |
| **S2** | Inconsistent with the design system; users feel it as friction. |
| **S3** | Cosmetic or internal; batch with adjacent work. |

## Ledger

| ID | Debt | Severity | Count | Owner | Removal |
|---|---|---|---|---|---|
| DD-01 | Bespoke `<button>` elements outside `ds.tsx`/`ui.tsx` | S2 | 93 | Frontend | Migrate screen by screen to `Button`/`IconButton`; lower the baseline each PR |
| DD-02 | Raw colour literals in UI modules | S2 | 7 | Frontend | Move remaining chart chrome onto tokens |
| DD-03 | Tiny HUD type below the 11 px floor (CSS only) | S2 | measured by audit | Design | Raise to 11 px minimum; density changes space, not type |
| DD-04 | Remaining English body copy when German is selected | S2 | most screens | Content + Frontend | Translate scenario narrative and long-form copy |
| DD-05 | No user interviews or usability sessions recorded | S1 | 0 of 5 per role | Research | Five sessions per role before the exit gate |
| DD-06 | Storybook is an in-product gallery, not a separate Storybook deployment | S3 | 1 | Frontend | Decide: publish the gallery as a static site, or adopt Storybook |
| DD-07 | Visual regression covers the stage and palette, not every component | S2 | partial | Frontend | Add snapshots per component and per theme |
| DD-08 | Pins/labels are SVG text, not a tiled vector label engine | S3 | 1 | Cartography | Replace when a real tile service lands |
| DD-09 | No customer assets, claims or adjuster labels | S1 | — | Customer | Blocked on customer data |
| DD-10 | No NPU hardware acceptance run | S1 | — | Platform | Blocked on target hardware |

## Rules

1. A PR may not increase a count in `web/design-lint-baseline.json`.
2. A PR that removes debt must lower the baseline in the same change.
3. New screens use only `ds.tsx` primitives and `tokens.css` values.
4. Any new colour must be added to `tokens.css` for every theme, or it is not a token.
5. “No AI claim without evidence” is a design rule: a claim ships with its source and time.

## Debt that is deliberately not debt

- SVG/canvas chart palettes in `Dashboard.tsx`, `Booth.tsx`, `MapView.tsx`,
  `WatchMap.tsx` and `StyleGuide.tsx` are allowlisted because they render data,
  not chrome.
- The in-product design system is intentional: it ships offline with the app and
  cannot drift from the running product.
