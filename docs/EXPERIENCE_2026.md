# GeoResponse — the 2026 product experience

This is the design brief behind **Phase 5** in [ROADMAP.md](ROADMAP.md). It is not a theme
refresh. It is a redesign of how the product feels, reads, moves and asks for a decision.

## What “2026” means here

2026 is not neon glass, an AI avatar or a 3D globe. For an operational decision tool it means:

> **Intent-first, spatial, calm, adaptive, explainable, accessible, fast and local-first.**

| Principle | Consequence |
|---|---|
| **Decision first** | The screen asks “what do we do?” before “what data do we have?” |
| **Spatial by default** | The map is the canvas; panels appear when the decision needs them. |
| **Intent before navigation** | A command surface and natural language come before deep menus. |
| **Calm telemetry** | Readable type, restrained colour, one accent, purposeful motion. |
| **Explainable AI** | Evidence, confidence, provenance, reversibility and a human signature. |
| **Adaptive** | Role, device, density, light/dark and reduced-motion preferences. |
| **Inclusive by default** | WCAG 2.2 AA, keyboard parity, screen-reader map alternatives. |
| **Local-first** | Fast, offline-capable, no CDN, no data leaving the customer network. |
| **Craft** | Typography, spacing, states, motion and copy are product features, not polish. |

## What it must not become

- Neon glassmorphism and glow used as a personality.
- A permanent 12-panel dashboard on every screen.
- An “AI” label with no agent, tools or grounded actions.
- Dark-only, desktop-only, mouse-only.
- 8–10 px type that looks like a HUD but cannot be read at 10 metres.
- A 3D globe, AR mode or voice always-on because it is 2026.
- Generative UI without approval, provenance and rollback.
- Surveillance drift under the banner of “monitoring”.

## Current audit — what stays, what goes

### Keep

- Map-first command surface.
- Cyan/amber/red semantic language (but less glow).
- Evidence + confidence + human-in-the-loop.
- Watch inbox and proactive narrative.
- Local-first/offline posture.
- Bespoke identity, not a component-template clone.

### Remove or rebuild

- **Tiny HUD type** (8–10 px labels, dense all-caps eyebrows).
- **Permanent panel grid** — mission, map, detail, timeline all competing.
- **Neon glass + heavy borders** as the default surface language.
- **Fixed 1600×1000 composition**; mobile is an adaptation, not a design target.
- **No command surface** and no conversational agent.
- **Dark-only**, no light mode, no density mode.
- **Hand-rolled charts** with inconsistent scales.
- **Procedural raster basemap** that reads as placeholder.
- **One-off CSS** rather than tokens and a component library.
- **Missing states** — loading, empty, error, offline, permission denied.
- **Color-only map semantics** and no screen-reader alternative.
- **No localization/RTL** despite a German customer.
- **No design instrumentation** — no task success, SUS, accessibility or performance baseline.

## Target experience metrics

| Area | 2026 target |
|---|---|
| Base text | Body 14–15 px, labels ≥ 11 px, HUD ≥ 12 px |
| Contrast | ≥ 4.5:1 body, ≥ 3:1 large text and UI |
| Keyboard | 100% of actions reachable; visible focus everywhere |
| Accessibility | WCAG 2.2 AA, screen-reader map/table alternative |
| Mobile | 390 × 844, no horizontal scroll, 44 px targets |
| Themes | Light, dark, system; high-contrast mode |
| Density | Comfortable and compact, user-selected |
| Initial JS | ≤ 250 KB gzip; map and workers lazy-loaded |
| LCP / INP / CLS | ≤ 2.0 s / ≤ 200 ms / ≤ 0.05 on a mid-range laptop |
| Command response | Palette opens < 100 ms; results < 150 ms |
| Decision path | Investigate → assign → hand off in ≤ 2 interactions |
| Offline | Full Watch/Stage/Analyst shell after one visit |
| Localization | English + German, RTL-ready layout |
| Trust | Every AI-backed action shows evidence and is reversible |

## Roles and devices

| Role | Primary job | First-class surface |
|---|---|---|
| Presenter | Tell the 90-second story | Stage, keyboard-driven |
| Analyst | Validate evidence and sign | Analyst workspace |
| Watch operator | Triage alerts and hand off | Watch inbox |
| Claims lead | Portfolio and SLA | Pilot/dashboard |
| Executive | One-screen situation | Briefing view |
| Field crew | Receive the right site | Mobile/PWA |
| Admin | Scope, recipients, models | Settings/governance |

## The 2026 maturity scorecard

A release is “2026-ready” only when:

- [ ] no text below 11 px in the product chrome;
- [ ] light + dark + high-contrast themes pass contrast;
- [ ] every action has a keyboard path and a visible focus state;
- [ ] the map has a non-visual alternative;
- [ ] the command palette can perform the top 10 tasks;
- [ ] the agent sidecar can preview, approve and undo an action;
- [ ] mobile 390 px has no horizontal scroll;
- [ ] the initial bundle is ≤ 250 KB gzip;
- [ ] LCP ≤ 2 s, INP ≤ 200 ms, CLS ≤ 0.05;
- [ ] the product works offline after one visit;
- [ ] five users per role complete the core task unaided;
- [ ] zero dark patterns and zero AI claims without evidence.

The checklist lives in **[ROADMAP.md Phase 5](ROADMAP.md#phase-5--2026-product-experience-planned)**.


## Measured after the first 2026 shell pass

| Check | Result |
|---|---|
| Lighthouse accessibility | **100** (best practices 100, SEO 100) |
| Initial JS/CSS | **113 KB gzip** (budget 250 KB) |
| Lazy routes | Watch, Analyst, Pilot, Booth, Method split; jsPDF on demand |
| Themes | System, light, dark, high contrast |
| Density | Comfortable and compact |
| Motion | Reduced-motion toggle + `prefers-reduced-motion` |
| Command palette | `Cmd/Ctrl+K`, grouped actions, sites, scenarios, Watch alerts |
| Agent | Live model path + local fallback, preview/apply/undo, refusal rules |
| Map alternative | Keyboard pan/zoom and accessible data table |
| Imagery | Real Sentinel-2 Ahr/Eifel/Cologne windows |
| Mobile | 390 px layout with bottom navigation |

Still open: the remaining visual migration, Storybook/visual regression, full German localization,
user research and the rollout gates. The Phase 5 checkboxes remain the source of truth.


## Second 2026 pass — verified

| Check | Result |
|---|---|
| Tokens | Single source in `web/src/tokens.css`; `@layer tokens → base → components → utilities` |
| Themes | System, light, dark, contrast; all token overrides |
| Design system | In-product gallery with Foundations, Components, Patterns and Anatomy (states, keyboard, screen reader) |
| Design lint | Ratchet with a 100-item baseline; new raw colour or bespoke button fails |
| Map clustering | Pins cluster below 1.6× zoom; clicking a cluster flies to it |
| Camera choreography | 460 ms interruptible transform; disabled by reduced motion |
| Deep links | `#view=…&scenario=…`; browser back/forward restores the view |
| Localisation | English and German shell, settings, palette, agent and app `lang` |
| E2E | 16 Playwright checks: stage, palette, themes, density, German, saved views, welcome tour, deep links, map orientation, map table, alert feedback, Pilot, role-based nav, axe, no horizontal scroll |
| Accessibility | axe clean on stage and Watch, desktop and mobile |
| Visual regression | Stage dark/light and command palette baselines |
| Mobile | 390 px bottom navigation; map controls no longer collide with the layer panel |
| Bundle | ~116 KB gzip initial; budget 250 KB |

Still open and deliberately unchecked: the remaining screen-by-screen visual
migration, every-component visual snapshots, full long-form German copy, user
interviews, SUS/task-success baselines, benchmark studies and the launch gate.


> **Where the remaining work lives:** Phase 7.B in [ROADMAP.md](ROADMAP.md) is the screen-by-screen
> 2026 programme (106 checkboxes). Phase 5 records what is already shipped.
