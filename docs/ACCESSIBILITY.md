# Accessibility statement — GeoResponse

GeoResponse targets **WCAG 2.2 level AA** across the stage, Watch, Analyst,
Pilot, Method and Booth surfaces.

## Conformance

| Area | Status |
|---|---|
| Keyboard: skip link, focus traps, map arrows and +/−, palette arrows/Enter | Implemented |
| Focus indicator in every theme | Implemented |
| Semantic landmarks and headings | Implemented |
| Screen-reader names for map pins, alerts, charts and controls | Implemented |
| Non-visual alternative for the map | Implemented — searchable data table |
| Charts | Implemented — data table behind each chart |
| Reduced motion | Implemented — setting and `prefers-reduced-motion` |
| Contrast | Tokenised; light, dark and high-contrast themes |
| Zoom | 200% text zoom supported without horizontal scroll (verified at 390 px) |
| Forms | Inline, programmatic errors with `role="alert"` |
| Live regions | Toast, offline banner and agent log use `role="status"` / `aria-live` |
| Touch targets | 44 px on navigation and primary actions |

## Known limitations

- Long-form scenario copy is English only; the shell and controls are German too.
- Some legacy HUD labels in the dark theme are below the 11 px floor; tracked in
  [DESIGN_DEBT.md](DESIGN_DEBT.md).
- Automated axe checks cover the stage, Watch and Pilot. They do not replace a
  manual audit with a screen-reader user, which is still open in
  [RESEARCH_2026.md](RESEARCH_2026.md).

## Feedback

Report an accessibility barrier at
https://github.com/jiuwendemos/georesponse/issues with the surface, the browser
and the assistive technology you use. We aim to acknowledge within two working
days.

## Verification

```powershell
cd web
npm run e2e -- --project=chromium
```

The Playwright suite runs axe on the stage, Watch and Pilot and fails on any
serious or critical violation.
