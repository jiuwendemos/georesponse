# Proactive monitoring pilot — 90 days

**Scope:** one corridor, one asset class, one change type. Shadow mode first.

## Offer

| Element | Detail |
|---|---|
| Cadence | Weekly, daily, event-surge or 24/7 |
| Sources | Sentinel-2 + Sentinel-1; optional Planet/Maxar/Airbus/ICEYE/Capella; customer drone |
| Coverage | Named scopes with a freshness SLO; blind spots disclosed |
| Alerts | Reviewable alerts with evidence, confidence, SLA and human validation |
| Integrations | Email/Slack/Teams/SMS/webhook; Jira/ServiceNow; claims/CMMS draft handoff |
| Deployment | SaaS, private cloud, on-premise or air-gapped |
| Price | Per km², per asset, per corridor, with a minimum commitment |

## 90-day plan

- **Days 1–10** — scope definition, purpose, exclusion zones, cadence, recipients, DPA, imagery access.
- **Days 11–30** — shadow mode: no customer-facing alerts. Measure precision, false positives, alert load.
- **Days 31–55** — analyst validation of the first N alerts per scope; enable notifications for green scopes.
- **Days 56–75** — live watch with SLA; weekly digest; tune thresholds and suppression.
- **Days 76–90** — readout: lead time, missed events, action conversion, cost per km², renewal proposal.

## Gates

| Gate | Target | Source |
|---|---|---|
| Shadow complete | 3 validated alerts per scope | `ValidationGate` |
| Precision | ≥ 0.80 against confirmed events | `pilot_report` |
| Alert load | ≤ 8 per analyst per 8h | `fatigue_budget` |
| SLA | 0 breaches in the last 30 days | `sla_breaches` |
| Coverage | freshness within the contract | `freshness_slo` |
| Safety | zero auto-approvals / auto-dispatch | audit + non-goal guard |
| Privacy | DPA, retention, scope review signed | privacy checklist |

The Watch → Settings → Pilot gates panel reads the same values. The demo pack has three SLA breaches,
so it shows a red gate; that is deliberate.

## Measurement

- **Lead time:** alert time minus the customer’s current detection time.
- **Missed-event rate:** confirmed events with no alert.
- **Precision / recall:** confirmed vs closed alerts.
- **Alert load:** alerts per analyst per shift.
- **Action conversion:** alerts that led to an inspection, claim or repair.
- **Cost:** per monitored km² and per actionable alert.
- **Coverage:** freshness, cloud gaps, blind spots.
- **Renewal intent:** expansion scope and named owner.

## Kill criteria (written before launch)

Stop or roll back if:

- precision < 0.60 for two consecutive months,
- alert load is above budget for two weeks,
- an SLA breach pattern cannot be fixed,
- a safety or privacy incident occurs,
- routing sends an alert to the wrong tenant or recipient.

## CRM fields

`name · role · organisation · segment · scopes · asset class · cadence · SLA · incumbent · imagery
provider · pilot start · shadow end · precision · lead time · renewal date · owner`.

## Post-pilot motion

- 48-hour readout with the recording, one-pager and Watch link.
- Convert to an annual monitoring subscription; credit the pilot fee.
- Expand one scope at a time; never jump from one corridor to a portfolio without a new gate.
