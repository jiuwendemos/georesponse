# LAIX decision layer

GeoResponse calls **LAIX** for every alert decision. LAIX is a pinned Python
dependency, not a copy inside this repository.

| Layer | Ownership |
|---|---|
| GeoResponse | alert detection, imagery, scopes, SLA clocks, analyst roster, alert store, proposals, approval, delivery, audit, API and UI |
| `georesponse/laix_adapter/` | translates an alert into a LAIX `Situation` and `Action` options; translates the LAIX decision back into GeoResponse state; creates proposals; records outcomes; plans sensing |
| LAIX | the generic decision: `wait`, `observe`, `guide`, `ask`, `act`, `verify` or `escalate` |

The flow is:

```
GeoResponse alert -> GeoResponse adapter -> LAIX Layer.decide() -> GeoResponse triage action
```

There is no native policy, shadow runtime or decision-engine feature flag. LAIX
is the only decision path.

## Pinned dependency

`pyproject.toml` pins LAIX to the release tag:

```toml
"laix @ git+https://github.com/michaelatamuk/laix.git@v0.7.0#subdirectory=packages/python/laix"
```

Install from the pin:

```powershell
py -m pip install "laix @ git+https://github.com/michaelatamuk/laix.git@v0.7.0#subdirectory=packages/python/laix"
```

For local co-development against the LAIX checkout:

```powershell
py -m pip install -e C:\Workspace\laix\packages\python\laix
```

Ordinary GeoResponse code changes do not need a reinstall.

## Upgrade LAIX

An upgrade is a deliberate commit, never a branch pointer:

1. Choose the LAIX release tag and read its integration notes.
2. Change the pinned string in `pyproject.toml` to that tag.
3. Reinstall the dependency.
4. Run `py -m pytest -q` and the web checks.
5. Run the real app and confirm a live alert decision.
6. Commit the pin change and the test updates together.

Do not point `pyproject.toml` at `main`.

## Adapter contract

| Adapter file | Responsibility |
|---|---|
| `spatial_context.py` | alert -> LAIX `Situation`, alert -> LAIX `Action` options, LAIX `Decision` -> GeoResponse view |
| `facade.py` | one `Layer`, one `DecisionRequest`, one decision, apply and execute |
| `approval_bridge.py` | an `act` decision becomes a GeoResponse proposal; execution uses the LAIX approval gate |
| `outcome_loop.py` | alert acknowledgement/resolution timestamps -> LAIX `Outcome` |
| `sensing_budget.py` | monitoring plan -> LAIX `ResourcePolicy` |

GeoResponse passes only generic LAIX fields. Scopes, alert IDs, analysts,
imagery sources and proposal storage stay in GeoResponse.

LAIX may return `observe`; GeoResponse treats it like `wait` for ownership: the
alert stays in the inbox and does not keep an implied assignee. `act` keeps the
existing routing and requires human approval. `escalate` tags the alert
`sla-escalated`.

## API

```powershell
GET /api/watch/decision-engine
```

Returns the installed LAIX package, policy and schema versions:

```json
{
  "engine": "laix",
  "package": "laix",
  "packageVersion": "0.7.0",
  "policyVersion": "2026.2",
  "schemaVersion": "1.1"
}
```

`GET /api/watch/overview` includes the same `decisionEngine` object. Mode and
parity fields are gone. The old `/decision-engine/evaluate` and
`/decision-engine/reset-parity` endpoints do not exist.

## Parity record

Before the local LAIX core was deleted, 9 open-alert decisions were captured in
`tests/fixtures/laix_parity_demo.json`.

After the switch to LAIX v0.7.0:

- 9 of 9 cases match on verb, action id, approval flag, confidence, applied
  constraints and receipt status.
- 3 of 9 rationale strings differ only in the policy wording: the captured core
  said `a hard deadline or SLA is already breached`; LAIX 2026.2 says
  `a hard deadline or commitment is already breached`.
- The captured native baseline and LAIX agree on `requires_approval` for all 9
  cases: only `act` carries the approval flag.

That wording change is reported by `tests/test_laix_adapter.py`; it is not
hidden by editing the fixture or the LAIX contract.

## Tests

```powershell
py -m pytest -q
cd web
npm test
npm run build
```

The adapter tests cover alert -> situation, alert -> options, decision -> view,
approval and proposal creation, execution receipts, outcome attribution,
sensing budget, the captured parity fixture, and the absence of the local
package, old mode flag and parity endpoints.

## Rollback

Revert the commit that switched GeoResponse to LAIX. Do **not** reintroduce a
second decision path or a mode flag. If LAIX itself is faulty, pin a previous
LAIX tag and run the same tests; the app keeps one decision path.

## Limits

- This is not a claim of LAIX 2027 targets.
- The policy is deterministic rules, not a learned policy.
- GeoResponse covers minutes-to-weeks decisions, not sub-second edge cases.
- The parity fixture is the bundled demo pack, not customer data.
- A customer workspace needs its own acceptance run after the upgrade.
