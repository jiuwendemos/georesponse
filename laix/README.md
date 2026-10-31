# LAIX core (extraction-ready)

A domain-neutral decision layer: **wait, ask, guide, act, verify, escalate**.

This directory is a standalone Python package. It imports only the standard
library and its own modules. Nothing here knows about GeoResponse, maps, alerts,
imagery or claims. The geospatial pack lives in
[`georesponse/laix_adapter`](../georesponse/laix_adapter).

## Why it is separate

The decision layer is the reusable part. The application is one adapter behind
it. Inverting the dependency now means the package can be lifted into LAIX later
without rewriting the product, and GeoResponse can keep working while that
happens.

```
app  ->  georesponse/laix_adapter  ->  laix  ->  (host skills / platform)
         geospatial knowledge           generic contracts
```

## Quick start

```python
from laix import Action, Belief, DecisionRuntime, Situation, iso

situation = Situation(
    id="sit-1",
    at=iso(),
    subject="example",
    beliefs=(Belief(id="risk", proposition="the risk is real", confidence=0.9),),
    attributes={"urgency": 0.9},
)
options = [
    Action(id="wait", verb="wait", name="keep_watching", expected_benefit=0.2),
    Action(id="assign", verb="act", name="assign_owner", expected_benefit=0.9,
           requires_approval=True, params={"owner": "team-2"}),
]

runtime = DecisionRuntime()
runtime.bridge.register("assign_owner", lambda action, context: {"assigned": action.params["owner"]})
decision = runtime.decide(situation, options)
receipt = runtime.execute(decision, actor="agent", approver="manager")
print(decision.verb, receipt.status)  # act executed
```

## Contracts

Ten records, all versioned at schema `1.0`:

| Contract | Carries |
|---|---|
| `Observation` | one measurement, source, confidence, cost, latency |
| `Belief` | a proposition, confidence, evidence, expiry |
| `Goal` | what the experience improves, priority, metric, deadline |
| `Constraint` | latency, cost, risk, interruption, approval, safety |
| `Action` | a candidate verb with benefit, cost, risk and reversibility |
| `Situation` | observations, beliefs, goals, constraints, phase, horizon |
| `Decision` | verb, chosen action, rationale, alternatives, approval flag |
| `Outcome` | metric, before, after, direction, attribution, label |
| `Receipt` | executed / refused / cancelled / failed / undone, with actor |
| `Trace` | ordered evidence for one decision |

The JSON Schema is generated from the dataclasses and committed at
[`schemas/laix-v1.schema.json`](schemas/laix-v1.schema.json). A test fails if the
committed file is stale.

## Policy

`DecisionPolicy` is rules first. No model call, no hidden score. First admissible
rule wins:

1. **safety** - a hard safety constraint blocks every action except wait
2. **escalate** - a hard deadline or SLA is already breached
3. **ask** - uncertainty is too high or confidence is below the floor
4. **verify** - a previous action still has an unverified outcome
5. **act** - urgency and confidence both clear their thresholds
6. **guide** - worth surfacing, not worth acting on
7. **wait** - keep observing silently

Hard constraints remove options before the rule order runs. Destructive actions
always require a human approver; without one the execution bridge returns a
`refused` receipt and performs no write.

## Runtime

`DecisionRuntime` wires the loop:

```
observe -> ExperienceState -> DecisionPolicy -> ExecutionBridge -> OutcomeLedger
```

Every decision gets a `Trace`; every execution gets a `Receipt`; every measured
change is recorded against the decision that caused it. `OutcomeLedger` supports
metric direction, so a lower time-to-decision is scored as an improvement.

## Resource policy

Cheap detectors run continuously. A deep call is admitted only when

```
information_gain * uncertainty >= threshold
```

and the deep-call, cost and latency budgets still allow it. The plan reports what
was skipped and why, so saved model calls are measured rather than asserted.

## Isolation guarantees

- `laix/` has no host imports. `tests/test_laix.py` scans the package and fails
  if one appears.
- All IDs, clocks and thresholds are explicit or injectable.
- The core is standard-library only.
- A host may persist `ExperienceState.snapshot()` wherever it likes.

## Test

```powershell
py -m pytest laix/tests
```

The same suite passes after the directory is moved into another repository.

## Extract into LAIX

1. Copy `laix/` into the LAIX repository (or publish it as `laix-core`).
2. Keep the host adapter in the host application; do not move geospatial code
   into the core.
3. Replace the deterministic policy with a learned policy only when the data
   justifies it; keep the same `PolicyRequest -> Decision` seam.
4. Implement the south interface against the target platform: named skills,
   cancel, approval, state read/write, event streaming, capability level.
5. Re-run the contract tests and the host parity harness.

## Not claimed

The LAIX brief's 2027 targets (+15% outcome, 85% intervention precision, -30%
deep-model calls, 60% reuse) are targets, not results. This package is a
candidate reference pack and a working implementation of the contracts, not a
claim of LAIX compliance.
