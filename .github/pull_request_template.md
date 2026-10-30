## What and why

<!-- The user problem, not the implementation. Link the issue. -->

## Design review gate

- [ ] Uses tokens from `web/src/tokens.css`; no new raw colour or magic spacing
- [ ] Uses `ds.tsx`/`ui.tsx` primitives; no new bespoke button
- [ ] All eight states defined: default, hover, active, focus, disabled, loading, error, empty
- [ ] Works in light, dark and high-contrast themes
- [ ] Works at 1440, 1024 and 390 px
- [ ] Keyboard reachable; focus visible; no pointer-only action
- [ ] Text ≥ 11 px; touch targets ≥ 44 px
- [ ] Reduced motion respected
- [ ] Any claim about data or AI links to its evidence and time

## Verification

```powershell
cd web
npm run test
npm run lint:design
npm run build
npm run budget
npm run e2e -- --project=chromium
```

- [ ] New debt? No — `web/design-lint-baseline.json` did not increase.
- [ ] Screenshots attached for visual changes (light and dark).

## Risk and rollback

<!-- What fails if this is wrong, and how do we reverse it? -->
