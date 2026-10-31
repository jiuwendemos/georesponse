# LAIX decision layer

GeoResponse now contains a real, extraction-ready decision module:

| Layer | Location | Knows about |
|---|---|---|
| Domain-neutral decision core | [`laix/`](../laix) | contracts, policy, state, execution, outcomes, resource policy |
| Geospatial adapter | [`georesponse/laix_adapter/`](../georesponse/laix_adapter) | scopes, alerts, SLAs, imagery sources, proposals |

The dependency points one way: **adapter -> laix**. The core never imports
GeoResponse, and a contract test fails if it ever does.

## What it decides

The north interface returns one of six verbs:

| Verb | GeoResponse meaning |
|---|---|
| `wait` | keep watching; do not wake an analyst |
| `ask` | request a better view, radar pass or analyst label |
| `guide` | show the alert and evidence, do not assign yet |
| `act` | assign an owner through an approved proposal |
| `verify` | check the analyst action and the SLA outcome |
| `escalate` | the SLA is breached; raise it to the on-call lead |

The decision carries a rationale, the rejected alternatives, the constraints that
applied and whether a human approval is required.

## Three modes, one flag

```
GEORESPONSE_DECISION_ENGINE = native | shadow | laix
```

| Mode | Who decides | What is recorded |
|---|---|---|
| `native` (default) | existing urgency and SLA rules | nothing extra; no behaviour change |
| `shadow` | native stays authoritative | LAIX decision, trace and parity comparison |
| `laix` | LAIX is authoritative | decision, trace, parity and an audit event |

Rollback is a flag flip and a restart. `native` is the default so an existing
deployment does not change on upgrade.

In `laix` mode, when LAIX decides `wait`, `ask` or `guide`, the alert is left
unassigned because no one is working it yet. On `act` the existing routing table
still supplies the owner; on `escalate` the alert is tagged `sla-escalated`.

## Measured parity

The parity harness compares native triage with LAIX on every open alert in the
local store. On the bundled demo pack:

```
9 open alerts, 9 agreements, agreementRate 1.0
```

Reproduce:

```powershell
py -m georesponse.cli laix-parity
```

The command uses a fresh adapter in `shadow` mode, evaluates the current store,
and exits non-zero if parity is below 100%.

Live endpoints:

```powershell
GET  /api/watch/decision-engine            # mode, policy/schema version, parity
GET  /api/watch/decision-engine/evaluate   # side-effect-free parity over open alerts
POST /api/watch/decision-engine/reset-parity
```

`GET /api/watch/overview` also includes `decisionEngine.mode` and the parity
summary.

## Approval and execution

LAIX never writes on its own. A decision that requires approval becomes a
GeoResponse proposal through `ApprovalBridge`:

1. `propose` creates a pending proposal in the existing `ProposalStore`.
2. A named human approves it through the existing API.
3. The approved proposal applies the change and can be undone.

The execution bridge also exposes direct handlers for `assign_alert`,
`handoff_alert` and `dismiss_alert`. They are only reached with an approver; the
default path is the proposal. A handoff remains a draft (`sent: false`).

## Outcome loop

`OutcomeLoop` uses timestamps the store already has:

- `time_to_acknowledge_minutes`
- `time_to_resolution_minutes`
- `analyst_verdict` (a label, explicitly excluded from attributed gain)

Outcomes support a direction, so a lower time is an improvement. Attribution is
only true when a matching execution receipt exists. No outcome data, customer
labels or user study is fabricated.

## Resource policy

`estimate(plan, uncertainty)` maps a monitoring plan to the LAIX resource policy:

- Sentinel and Landsat are cheap, continuous;
- commercial tasking and the deep change model are deep calls;
- deep calls are admitted only when information gain times uncertainty clears
  the threshold and the plan budget allows it;
- the result lists every skipped call and why.

Example: a `sentinel-2 + planet` plan with a €100 budget allows Sentinel and
skips Planet with `cost budget exhausted`. The same plan at €2,500 allows Planet.
Source prices are illustrative and must be replaced by contract prices before an
operational budget decision.

## Files

| File | Role |
|---|---|
| `laix/contracts.py` | ten versioned contracts |
| `laix/state.py` | goals, phase, belief merge, decay and expiry |
| `laix/policy.py` | deterministic verb selection and constraint admission |
| `laix/execution.py` | approval gate, execute, cancel, undo, receipts |
| `laix/outcome.py` | directed metrics and attributed summary |
| `laix/resources.py` | deep-call admission under budget |
| `laix/runtime.py` | the facade and decision traces |
| `laix/schema.py` | generated JSON Schema and structural checks |
| `georesponse/laix_adapter/spatial_context.py` | alert -> situation and options |
| `georesponse/laix_adapter/facade.py` | modes, parity, status, evaluation |
| `georesponse/laix_adapter/approval_bridge.py` | LAIX action -> proposal registry |
| `georesponse/laix_adapter/outcome_loop.py` | alert timeline -> outcome |
| `georesponse/laix_adapter/sensing_budget.py` | plan -> resource policy |

## Tests

```powershell
py -m pytest laix/tests tests/test_laix_adapter.py
```

- `laix/tests` is portable and uses no GeoResponse import.
- `tests/test_laix_adapter.py` covers native/LAIX parity, shadow and authoritative
  modes, engine integration, proposal approval, outcome attribution and the
  sensing budget.

## Migration status

| Slice | State |
|---|---|
| 1. Contracts, policy, state, schema, tests | done |
| 2. GeoResponse adapters and shadow parity | done |
| 3. Facade switch with rollback | done (`native` default) |
| 4. Package extraction | ready; `laix/` is self-contained |

## Limits

- This is not a claim of LAIX compliance. LAIX's 2027 targets are targets.
- The policy is deterministic rules, not a learned policy. That is deliberate:
  safety rules first.
- GeoResponse covers the minutes-to-weeks decision band, not LAIX's sub-second
  edge cases.
- The adapter's default analyst roster and commercial imagery prices are demo
  values, not customer data or contract prices.
- Parity is measured on the bundled demo pack. A customer workspace needs its
  own parity run before switching the flag.
