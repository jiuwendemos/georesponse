# LAIX handoff — v1

Branch: `laix/handoff-v1`
Tag: `laix-handoff-v1`
Handoff content commit: `8b4a812`

This is a behaviour-preserving handoff pass. The policy, rule order, thresholds,
public contract names, contract fields, adapter and parity harness are unchanged.
`native` remains the default decision-engine mode.

## Module paths and line counts

| Path | Lines | Role |
|---|---:|---|
| `laix/__init__.py` | 81 | public exports |
| `laix/contracts.py` | 347 | ten versioned dataclasses and shared helpers |
| `laix/state.py` | 158 | goals, phase, belief merge, decay and expiry |
| `laix/policy.py` | 256 | deterministic verb selection and constraint admission |
| `laix/execution.py` | 140 | approval gate, execute, cancel, undo and receipts |
| `laix/outcome.py` | 100 | directed metrics and attributed summary |
| `laix/resources.py` | 94 | deep-call admission under budget |
| `laix/runtime.py` | 203 | runtime facade and decision traces |
| `laix/schema.py` | 139 | schema generation and structural checks |
| `laix/schemas/laix-v1.schema.json` | 953 | committed, generated schema |
| `laix/contract/README.md` | 43 | contract freeze note |
| `laix/fixtures/replay.json` | 2240 | golden replay fixture |
| `laix/tests/test_laix.py` | 266 | portable contract and policy tests |
| `laix/tests/test_replay.py` | 96 | golden replay tests |
| `laix/tests/test_isolation.py` | 114 | import and domain-noun guards |
| `laix/README.md` | 106 | package documentation |

## Public API

| Symbol | What it does |
|---|---|
| `DecisionRuntime` | `decide`, `execute`, `cancel`, `undo`, `measure`, `schedule`, `trace`, `stats` |
| `DecisionPolicy` | deterministic `PolicyRequest -> Decision`; `PolicyConfig` holds the frozen thresholds |
| `ExperienceState` | goals, constraints, beliefs, decay, expiry, history and snapshot/restore |
| `ExecutionBridge` | named skill handlers, approval gate, cancel, undo and receipts |
| `OutcomeLedger` | directed metric recording, attribution coverage and summaries |
| `ResourcePolicy` | cheap/deep call admission under information-gain and budget limits |

Supporting exports: `Action`, `Belief`, `Constraint`, `Decision`, `Goal`,
`Observation`, `Outcome`, `Receipt`, `Situation`, `Trace`, `PolicyRequest`,
`PolicyConfig`, `Budget`, `ResourcePlan`, `SensingOption`, `iso`, `parse_iso`,
`confidence_band`, `decide`.

## Dependencies

**Standard library only.** The package imports:

`dataclasses`, `datetime`, `typing`, `uuid`, `json`, `types`, `pathlib`,
`collections`, `ast` (tests only), plus its own modules.

It does not import `georesponse`, FastAPI, SQLite, numpy or any other third-party
package. `laix/tests/test_isolation.py` enforces both the import rule and the
absence of executable GeoResponse domain nouns.

## Test commands and results

From the GeoResponse repository:

```powershell
py -m pytest laix/tests tests/test_laix_adapter.py
```

Result at handoff: **52 passed** (34 portable package tests plus 18 adapter
tests; the full app suite is larger).

Parity:

```powershell
py -m georesponse.cli laix-parity
```

Result at handoff: **9 open alerts, 9 agreements, agreementRate 1.0**, exit `0`.

Standalone copy, outside the repository:

```powershell
$copy = "C:\Users\m00645993\AppData\Local\Temp\opencode\laix-handoff-copy"
if (Test-Path $copy) { Remove-Item -Recurse -Force $copy }
New-Item -ItemType Directory -Path $copy | Out-Null
Copy-Item -Recurse "C:\Workspace\openjiuwendemos\georesponse\laix" "$copy\laix"
Set-Location $copy
$env:PYTHONPATH = $copy
py -c "import laix; print(laix.__file__); print(laix.SCHEMA_VERSION); print(laix.POLICY_VERSION)"
py -m pytest laix/tests -q
```

Result:

```text
C:\Users\m00645993\AppData\Local\Temp\opencode\laix-handoff-copy\laix\__init__.py
1.0
2026.1
34 passed
```

The copy contains no GeoResponse code and no GeoResponse path on `sys.path`.

## Generic versus geospatial

| Layer | Location | Owns |
|---|---|---|
| Generic LAIX core | `laix/` | contracts, beliefs, policy, execution, outcomes, resource policy, replay |
| Geospatial adapter | `georesponse/laix_adapter/` | scopes, alerts, SLA clocks, imagery sources, proposals, native parity baseline |
| Host application | `georesponse/` | API, store, UI, demo pack, production wiring |

The dependency points one way: **adapter -> laix**. The adapter may change with
GeoResponse; the core must not import it.

## Packaging metadata for extraction

Place this at the root of the future `laix-core` repository. Do not move code
inside a second nested package.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "laix-core"
version = "0.1.0"
description = "LAIX decision layer: versioned contracts and a deterministic policy for wait, ask, guide, act, verify and escalate."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
dependencies = []

[tool.setuptools.packages.find]
where = ["."]
include = ["laix", "laix.*"]
```

The existing repository `pyproject.toml` already includes `laix*` in package
discovery, so the package can be imported and tested in place. The snippet above
is only for the eventual standalone repository.

## Three modes

Mode is selected with `GEORESPONSE_DECISION_ENGINE`, read when the API process
starts:

```text
GEORESPONSE_DECISION_ENGINE = native | shadow | laix
```

| Mode | Who decides | What is recorded |
|---|---|---|
| `native` (default) | existing urgency and SLA rules | nothing extra; no behaviour change |
| `shadow` | native remains authoritative | LAIX decision, trace and parity comparison |
| `laix` | LAIX is authoritative | decision, trace, parity and an audit event |

Rollback is a flag flip and a restart. `native` stays the default so an upgrade
does not change live triage. In `laix` mode, `wait`, `ask` and `guide` clear an
implied owner; `escalate` tags the alert with `sla-escalated`.

## Measured parity and caveat

On the bundled demo pack, native and LAIX agree on **9 of 9 open alerts**
(100%). The parity harness is `py -m georesponse.cli laix-parity`; it uses a fresh
adapter in `shadow` mode and exits non-zero below 100%.

Caveat: this is parity on the bundled synthetic demo pack, not a customer
workspace and not evidence of LAIX's 2027 targets. A customer deployment must run
its own parity pass before switching to `laix`.

## Golden replay

`laix/fixtures/replay.json` contains **10 cases**:

- 9 real open-alert decisions captured from the demo store at
  `georesponse@db31f7e`;
- the quick-start case from `laix/README.md`.

The fixture contains only portable LAIX contracts. Live timestamps are
normalised to `2026-01-01T00:00:00+00:00`; generated IDs are replaced by stable
case/action IDs. `laix/tests/test_replay.py` replays each case through
`DecisionRuntime` and checks verb, action, approval flag, rationale, confidence,
applied constraints, policy version and receipt status/action/approver.

At handoff: **10 cases, 0 diffs**.

## Known limits

- The policy is deterministic rules, not a learned policy. Safety rules first is
  deliberate.
- `sla_breached` is a portable attribute name carried over from GeoResponse, and
  the frozen rationale text says "SLA". These are the only executable domain
  nouns in the core; see `EXECUTABLE_EXCEPTIONS` in
  `laix/tests/test_isolation.py`.
- The approval constraint marks every decision as requiring approval, including
  non-writes. This is conservative and frozen for the handoff; changing it is a
  policy change.
- The replay fixture captures current behaviour, not a universal truth. It will
  fail if the policy or contract changes; update it deliberately.
- GeoResponse covers the minutes-to-weeks decision band, not LAIX's sub-second
  edge cases.
- Default analyst names and commercial imagery prices in the adapter are demo
  values, not customer data or contract prices.
- LAIX 2027 targets are targets, not results. This is a candidate pack, not a
  claim of LAIX compliance.

## Extraction steps

1. Copy `laix/` into the LAIX repository as the top-level `laix` package.
2. Add the `pyproject.toml` snippet above at the repository root.
3. Keep `georesponse/laix_adapter/` in GeoResponse. Do not move scopes, alerts,
   SLA clocks, imagery or proposals into the core.
4. Run `py -m pytest laix/tests` in the extracted repository. It must pass with
   no GeoResponse installation.
5. Publish `laix-core` only after the LAIX contract review; this handoff does not
   publish anything.
6. Point GeoResponse at the published package, keep the adapter, run
   `py -m georesponse.cli laix-parity`, then switch `GEORESPONSE_DECISION_ENGINE`
   from `shadow` to `laix` when parity is 100%.
7. Keep `native` available as the rollback for at least one release.
