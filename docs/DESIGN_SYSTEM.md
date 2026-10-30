# GeoResponse design system — 2026

The design system ships inside the product. It is a modal in the running app
(`Settings → Open design system`) with four tabs: Foundations, Components,
Patterns and Anatomy. It is also the contract every screen is reviewed against.

## Versioning

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-29 | Tokens, themes, density, motion, primitives, accessible map table |
| 1.1 | 2026-10-30 | Token extraction and `@layer` architecture; clustering and camera; anatomy and accessibility matrix; German shell; deep links |

The version is shown in the design-system footer. The changelog is this table.

## Tokens

Single source: `web/src/tokens.css`.

- **Colour** — canvas, surface, ink, muted, soft, lines, one accent (`--cyan`),
  semantic `--red`, `--amber`, `--green`, `--violet`.
- **Type** — display, heading, title, body, label; 11 px legibility floor.
- **Space** — 4-point grid from `--space-1` (4 px) to `--space-7` (48 px).
- **Shape** — `--radius-sm`, `--radius`, `--radius-lg`, `--shadow`.
- **Motion** — `--motion-fast` 120 ms, `--motion-normal` 220 ms, `--motion-slow` 360 ms, `--ease-out`.
- **Layout** — `--touch-target` 44 px, `--content-max` 1480 px.

Layer order is declared once in `web/src/index.css`:
`tokens → base → components → utilities`.

## Themes

- **System** follows the OS.
- **Light** for bright rooms.
- **Dark** is the operational default.
- **Contrast** is pure black/white with a yellow accent.

Every theme is a token override, never a component fork.

## Components

Primitives live in `web/src/components/ds.tsx` and `ui.tsx`:

`Button`, `IconButton`, `Badge`, `Card`, `Field`, `TextInput`, `Segmented`,
`EmptyState`, `Spinner`, `Kbd`, `Modal`, `Icon`, `TopBar`, `MobileNav`, `Toast`,
plus the map, chart, timeline and sparkline primitives.

Every component defines default, hover, active, focus, disabled, loading, error
and empty states. The Anatomy tab lists keyboard and screen-reader behaviour for
each.

## Metrics

| Metric | Target | Current |
|---|---|---|
| Lighthouse accessibility | 100 | 100 |
| Lighthouse best practices | 100 | 100 |
| Lighthouse SEO | 100 | 100 |
| Initial JS/CSS (gzip) | ≤ 250 KB | ~116 KB |
| Lazy routes | all secondary views | Watch, Analyst, Pilot, Booth, Method |
| Contrast | WCAG AA in every theme | enforced by tokens |
| Touch target | ≥ 44 px | 44 px on navigation and primary actions |

## Adoption lint

```powershell
cd web
npm run lint:design          # fails on new debt
npm run lint:design:update   # lower the baseline after a migration
```

The baseline is `web/design-lint-baseline.json`. See
[DESIGN_DEBT.md](DESIGN_DEBT.md).

## Visual regression

```powershell
cd web
npm run e2e:update   # regenerate baselines on the dev workstation
npm run e2e:visual   # assert stage (dark/light) and palette
```

Baselines are per-OS and intentionally not shared across platforms. CI runs the
functional and axe suite; the visual suite runs on the workstation.

## Accessibility

- axe runs against the stage and Watch on every push (Playwright).
- Keyboard: skip link, focus traps, map arrows and +/-, palette arrows/Enter,
  segmented controls as radio groups.
- Reduced motion is both a setting and a `prefers-reduced-motion` query.
- The map has a keyboard-operable data table alternative.
