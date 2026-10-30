# Research & measurement plan — 2026 experience

This document is the instrument the Phase 5 exit gate uses. It separates what has
actually been measured from what still requires users.

## Status

| Activity | Status |
|---|---|
| Instrumented product metrics (Lighthouse, bundle, axe) | **Done** |
| Task-completion script and scoring sheet | **Done** — below |
| Usability sessions per role | **Not run** — needs five users per role |
| Benchmark of five operational products | **Not run** — needs a research owner |
| SUS / task-success baseline | **Not run** — needs sessions |

No interview, SUS score or benchmark is claimed as complete.

## Roles to recruit

| Role | What they do in the product | Sessions |
|---|---|---|
| Presenter | Drives the stage and booth narrative | 5 |
| Watch operator | Triages alerts, manages scopes and coverage | 5 |
| Analyst | Reviews evidence, approves, assigns, exports | 5 |
| Claims lead | Reads assessments and claims drafts | 5 |
| Field responder | Uses the field order on a phone | 5 |
| Admin | Manages tenant, channels, integrations | 5 |

## Task script

Each session runs the same six tasks against the live build. Record completion,
time, errors and a think-aloud note.

1. **Orient** — open the app and say what changed in the last 24 hours.
2. **Triage** — find the highest-risk open alert and explain why it is ranked first.
3. **Verify** — open the evidence and say whether you trust it; name the source.
4. **Decide** — assign a team and produce a field order.
5. **Reverse** — dismiss an alert with a reason, then undo it.
6. **Ask** — use the agent to summarise a scope and approve or reject its proposal.

### Scoring sheet

| Field | Value |
|---|---|
| Participant / role | |
| Task | 1–6 |
| Completed (Y/N) | |
| Time on task (s) | |
| Errors | |
| Assistance required | |
| Confidence (1–5) | |
| Think-aloud note | |

## Metrics and instruments

Targets are set so a regression is visible before a pilot notices it.

| Metric | Target | Instrument |
|---|---|---|
| Lighthouse accessibility | 100 | Lighthouse, CI |
| Lighthouse best practices / SEO | 100 | Lighthouse, CI |
| Initial JS/CSS gzip | ≤ 250 KB | `npm run budget` |
| LCP (4G, Moto G-class) | ≤ 2.5 s | Lighthouse mobile |
| INP | ≤ 200 ms | field / lab |
| CLS | ≤ 0.1 | Lighthouse |
| axe serious/critical | 0 | Playwright + axe |
| Task success | ≥ 90% | sessions |
| SUS | ≥ 80 | sessions |
| Time to first decision | ≤ 60 s | sessions |
| Agent proposal acceptance | tracked, not targeted | product telemetry |

### Reproduce the measured numbers

```powershell
cd web
npm run build
npm run budget
npm test
npm run e2e -- --project=chromium
```

Lighthouse is run against the built app at 1440×900 for desktop and the Pixel 7
profile for mobile.

## Benchmark frame (to be filled by the research owner)

Score each product 1–5 on: density, command surface, map craft, agent
transparency, keyboard coverage, mobile field use.

| Product | Density | Command | Map | Agent | Keyboard | Mobile |
|---|---|---|---|---|---|---|
| GeoResponse (current) | 3 | 4 | 4 | 4 | 4 | 3 |
| — | | | | | | |
| — | | | | | | |
| — | | | | | | |
| — | | | | | | |

## Exit gate

The 2026 scorecard in [EXPERIENCE_2026.md](EXPERIENCE_2026.md) is green when:
instrumented metrics pass, five sessions per role are recorded, task success is
≥ 90%, SUS ≥ 80, and no S1 debt remains in [DESIGN_DEBT.md](DESIGN_DEBT.md).
