# LAIX contract freeze — v1.0

**Schema version:** `1.0`
**Policy version:** `2026.1`
**Normative shape:** [`../schemas/laix-v1.schema.json`](../schemas/laix-v1.schema.json)

The generated schema is normative for the **shape** of every contract. It is
generated from the dataclasses in [`../contracts.py`](../contracts.py) by
[`../schema.py`](../schema.py) and committed as a versioned artefact. Do not edit
the JSON by hand; run:

```powershell
py -c "from laix.schema import write_schema; write_schema()"
```

The staleness test regenerates the document and fails if the committed file
differs:

```powershell
py -m pytest laix/tests/test_laix.py -k schema
```

The **policy rules** are not part of the JSON Schema. They are documented in
[`../README.md`](../README.md) and implemented in [`../policy.py`](../policy.py).
Changing thresholds, rule order or the six verbs is a policy change, not a
schema change, and needs its own review.

## The ten contracts

| # | Contract | Version field | Purpose |
|---|---|---|---|
| 1 | `Observation` | `schema_version` | one measurement, source, confidence, cost and latency |
| 2 | `Belief` | `schema_version` | a proposition with confidence, evidence and expiry |
| 3 | `Goal` | `schema_version` | what the experience improves, its priority, metric and deadline |
| 4 | `Constraint` | `schema_version` | latency, cost, risk, interruption, approval or safety limit |
| 5 | `Action` | `schema_version` | a candidate verb with benefit, cost, risk, reversibility and approval need |
| 6 | `Situation` | `schema_version` | observations, beliefs, goals, constraints, phase and horizon |
| 7 | `Decision` | `schema_version` | chosen verb, action, rationale, alternatives and approval flag |
| 8 | `Outcome` | `schema_version` | measured metric, before/after, direction, attribution and label |
| 9 | `Receipt` | `schema_version` | executed, refused, cancelled, failed or undone execution record |
| 10 | `Trace` | `schema_version` | ordered evidence for one decision |

Every record also carries `schema_version = "1.0"` so a future change can be
detected and migrated instead of silently reinterpreted.

## Frozen in this handoff

- Public type names and contract field names.
- The six verbs: `wait`, `ask`, `guide`, `act`, `verify`, `escalate`.
- JSON Schema shape and version.
- Policy rule order and thresholds.

Not frozen: the canonical LAIX contract itself. This is a candidate pack. If LAIX
changes the north/south contract, add a new schema version and migrate; do not
rewrite v1 in place.
