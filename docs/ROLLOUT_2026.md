# Rollout plan — 2026 experience

The redesign ships behind flags and in slices, never as a big-bang replacement.

## Stages

| Stage | Audience | Gate |
|---|---|---|
| 0. Internal | Team | CI green, axe 0, budget pass |
| 1. Design partners | 2–3 friendly analysts | Task script in [RESEARCH_2026.md](RESEARCH_2026.md) passes for them |
| 2. Pilot tenant | One customer tenant | No S1 debt; support runbook ready |
| 3. General | All tenants | Scorecard green; rollback rehearsed |

## Flags and escape hatches

| Control | Behaviour |
|---|---|
| `data-theme` | Tokens only; no component fork |
| `data-density` | Spacing only; never type below 11 px |
| `data-motion` | Disables transitions; honours OS preference |
| `data-language` | Shell translated; long-form copy tracked in the debt ledger |
| `GEORESPONSE_MODE` | `auto` / `production`; production disables seeded data |
| Command palette | Always available; actions are the same functions as the UI |
| Agent panel | Live model when configured; otherwise clearly labelled local tools |

## Migration order

1. Shell and tokens (done).
2. Command palette and navigation (done).
3. Map craft: clustering, camera, table (done).
4. Watch, Analyst, Pilot, Method, Booth screens (in progress).
5. Long-form German copy and research loop (open).

## Rollback

- **Static app:** redeploy the previous commit; the service worker cache name is
  versioned and the next load replaces the shell.
- **Design system:** all changes are tokens or additive components; reverting the
  token file restores the previous look without touching screens.
- **Agent:** set `GEORESPONSE_AGENT_BACKEND` to the last known backend; the UI
  falls back to local tools and says so.
- **API:** Postgres store can be bypassed with SQLite for a single-box rollback;
  no schema migration is destructive.

## Communications

- Design partners get a one-page “what changed” note per stage.
- Support gets the three most likely questions and the rollback command.
- No “AI is live” claim is made unless `doctor` reports the agent configured.

## Gates

- [x] CI: unit tests, build, budget, design lint, axe
- [x] Accessibility 100 on the stage
- [x] Accessible map alternative
- [ ] Five sessions per role recorded
- [ ] Pilot tenant sign-off
- [ ] General availability

See [DESIGN_DEBT.md](DESIGN_DEBT.md) and [RESEARCH_2026.md](RESEARCH_2026.md).
