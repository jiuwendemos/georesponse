# Proactive monitoring — design & operation

> Proactive detection. Human decision. Auditable action.

The proactive phase is built in `georesponse/proactive/` and surfaced in the **Watch** tab. It watches a
defined scope on a cadence, detects change against a seasonal baseline, opens a reviewable alert, and
routes it to a human. It never approves a claim, dispatches a crew, or monitors people.

## What is running

```
schedule ─► acquire ─► baseline ─► confirm ─► alert ─► incident ─► route ─► notify ─► human
                                  │            │
                                  └─ no alert ─┘
                                  (recorded, not a failure)
```

| Layer | Module | What it does |
|---|---|---|
| Domain | `models.py` | Scope, plan, acquisition, baseline, alert, incident, notification, forecast, model, preferences, validation, costs |
| Store | `store.py` | SQLite WAL, tenant-scoped JSON rows, hash-chained audit, backup/restore, retention |
| Schedule | `scheduler.py` | Cadence, idempotency, overlap de-dupe, commercial approval, budget, retries, readiness, calendar, air-gap import, cost anomaly |
| Baseline | `baseline.py` | Seasonal statistics, trend/abruptness, multi-temporal and optical/SAR confirmation, adaptive thresholds, construction/vegetation/erosion, suppression, drift, backtest, calibration, feedback |
| Anticipation | `anticipation.py` | Forecast ingest, pre-event watchlist, lead time, uncertainty, tasking trigger, seasonal calendar, heatmap, scenario simulation |
| Alerts | `alerts.py` | Schema, urgency, dedupe, incident grouping, state machine, routing, SLA, bulk actions, why panel, handoff, fatigue, digest, mobile card |
| Notifications | `notifications.py` | Email, Slack, Teams, SMS, pager, HMAC webhook, quiet hours, least privilege, outbox, retries, dead letters |
| Integrations | `integrations.py` | Jira, ServiceNow, Guidewire, Duck Creek, Maximo, SAP, ArcGIS, QGIS, dispatch, SIEM — all draft-only |
| Governance | `governance.py` | Model registry, explainability, false-alarm cost, overrides, precision/calibration, privacy, Fernet tenant keys, kill switch, rate limits, on-call, validation gate, non-goals |
| Ops | `ops.py` | Quotas, secrets vault, job queue, object store, air-gap cycle, replay, backup/restore drill, load test, blue/green, Postgres mirror |
| Orchestration | `engine.py` | Observation → finding → alert → incident → route → notification; tick, dashboard, pilot gates, handoff |
| Demo | `demo.py` | Six scopes, 24 alerts, five incidents, forecasts, coverage, costs, models, prefs, pilot metrics |
| UI | `web/src/components/Watch.tsx` | Inbox, scopes, coverage, digest, settings, pilot gates, governance, scope drawing |

## Monitoring charter

**The service does:** watch the agreed scope, disclose freshness and blind spots, produce evidence-backed
alerts, route them to named humans, record every decision, and hand off drafts into claims, CMMS and field
tooling.

**The service does not:** approve claims, dispatch crews, monitor people or private life, use live video,
run facial recognition, or promise that a model alert is ground truth.

## The scope contract

Every scope declares **one purpose, one asset class, one cadence, one freshness SLO, one recipient
group, one budget, and exclusion zones**. The Watch UI onboarding wizard creates exactly that. A scope
can be paused, resumed, or killed without deleting its audit trail. “No action” is a first-class
decision with a reason.

Subscription tiers: weekly, daily, event-surge, 24/7.

## Alert lifecycle

```
new → acknowledged → assigned → investigating → resolved
  └───────────────└──────────────└──────────────→ dismissed (reason required)
```

- Deduplication groups nearby, same-type alerts within six hours into one incident.
- Urgency = severity, confidence, value at risk, population, access.
- Routing uses scope/severity rules, then on-call round-robin.
- SLA timers are set from the plan; breach scans run every tick.
- Bulk actions are capped at 50 and audited.
- First N alerts per scope can be gated for analyst validation before any customer notification.
- “Why this alert” shows threshold, trend, confirmation, fusion, suppression and evidence.
- Handoff creates a *draft* assessment, claim, inspection or dispatch — never an action.

## Anticipation

Forecasts are joined to scope exposure. The watchlist shows probability, uncertainty interval, lead
time, value/population at risk and a tasking trigger. Pre-positioning is a recommendation, not a
dispatch. Scenario simulation answers “if the water reaches X, what is cut off?” and is labelled as a
scenario, not a forecast.

## Trust and safety

- Human review is mandatory on every customer-facing alert.
- No automated claim approval, no automatic dispatch.
- No monitoring of people, protests, private life or protected groups.
- No live video, no facial recognition.
- Tenant isolation, per-tenant Fernet keys for sensitive payloads, least-privilege recipients.
- Hash-chained audit for scope, plan, alert, notification, validation and model events.
- Kill switch stops acquisition, alerts and notifications for a tenant.
- Model registry pins every alert to a version and supports rollback.
- Shadow mode: the first N alerts per scope are not sent to the customer until an analyst validates.
- Launch gate: precision ≥ 0.80, no SLA breaches, alert load within budget, shadow validations complete.
  The demo pack is seeded with three SLA breaches, so the gate honestly shows **red**.

## Operational runbook

1. `py -m georesponse.datapack` — rebuild the demo pack, including `proactive.json`.
2. `py -m georesponse.cli load-test --scopes 1000 --alerts 10` — 1,000 scopes / 10,000 alerts.
3. `py -m georesponse.cli drill` — backup, mutate, restore, verify audit.
4. `py -m georesponse.cli airgap --scope scope-ahr-corridor --folder <dir>` — air-gapped import.
5. `py -m georesponse.cli serve` — Watch API at `/api/watch/*`.
6. Watch → Settings → Governance — kill switch, outbox, model registry, pilot gates.

Scheduler worker (cron or container):

```powershell
py -c "from georesponse.proactive.api import engine, store; import json; print(json.dumps(engine.run_tick(tenant='demo', forecasts=store.list_forecasts()), indent=2))"
```

## API surface

`/api/watch/overview`, `/scopes`, `/alerts`, `/alerts/{id}/action`, `/alerts/bulk`,
`/incidents/{id}/view`, `/coverage`, `/dashboard`, `/pilot`, `/digest`, `/governance`,
`/preferences`, `/notifications/outbox`, `/forecasts`, `/watchlist`, `/simulate/{scope}`,
`/observations`, `/tick`, `/costs`, `/audit`, `/kill-switch`, `/models/*`,
`/integrations`, `/alerts/{id}/handoff/{target}`, `/jobs`, `/objects`, `/metrics`, `/quotas`,
`/deployment`, `/postgres-mirror`.

## Demo data & honesty

`data/proactive.json` is seeded: six scopes across utility, insurance, construction, agriculture and
mining; 24 alerts; five incidents; forecasts; baselines; acquisitions; costs; notifications; models.
The lifecycle algorithms are real. The customer names, alerts and pilot numbers are demo data.
The launch gate is deliberately not all green.
