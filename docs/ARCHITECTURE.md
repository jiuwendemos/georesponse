# Architecture

## Shape

```
imagery ──► tiling ──► change ──► context ──► ranking ──► assessment ──► human ──► map + report
             │           │          │           │            │              │
         GeoTIFF      cloud      OSM/asset   weights      claims        audit chain
         CRS norm     severity   population  disclosure   template      GeoJSON/PDF
```

There are two runtimes:

1. **Static web app** (`web/`) — the stage, booth, analyst workspace and dashboards. It reads a
   precomputed data pack and does the interactive work (time scrub, re-rank, review, vote, export).
2. **Python pipeline** (`georesponse/`) — builds the demo pack and provides the pilot API, detection,
   context, ranking, assessment, exports, audit, connectors and deployment helpers.

The app is intentionally static-first: the stage must run with the network cable unplugged. The API is
optional and adds review persistence, server-side PDFs and integrations.

## The map

The map is a custom SVG renderer, not MapLibre/Leaflet. Reasons:

- No WebGL dependency, no tile server, no glyph CDN.
- The whole scene is local GeoJSON + one basemap raster, so offline is trivial.
- Pins, coverage circles and flood frames are DOM nodes we can style and test.
- Bundle is ~720 kB (225 kB gzipped) instead of >1.8 MB.

Interactions: drag to pan, wheel/controls to zoom, click a pin, layer toggles, time slider, play/pause,
zoom-out reveal, coverage preview on hover, analyst focus on selection. The stage and analyst views use
the same component with different chrome.

## Data pack

`py -m georesponse.datapack` writes `web/public/data/`:

```
index.json                  scenario picker, model version
scenarios/<id>.json         meta, 18 sites, timeline, map layers, ranking, assessments, field order
basemaps/<id>.png           procedural orthophoto-like raster
scenes/<id>-before/after    whole-scene pair for provenance
evidence/<id>/*.png         per-site before/after crops
pilot.json                  accuracy, false positives, time saved, cost
precision-recall.json       per-event report
monitoring.json             baseline alerts
regional-events.json        dashboard map
privacy.json                review checklist
integrations.json           claims/GIS/field adapters
npu.json                    deployment profile
model-card.json             damage-head fit and metrics
packs.json                  agriculture/mining/government/partner
pilot-offer.json            90-day offer
```

Everything is deterministic: same seed → same flood, same false positive, same 42 minutes.

## Ranking

```
score = 0.28·extent + 0.18·confidence + 0.22·value + 0.16·access + 0.16·population
```

Each factor is min-max normalised across the active candidates. A rejected site is removed and the
remaining candidates are re-normalised and re-sorted, which is why the list visibly re-orders. Every
score carries its contributions, shown as bars in the site card and in the audit/export.

## Human in the loop

- No automatic approvals. The API creates draft claims/work orders only.
- Rejections keep the reason, imagery, model version and analyst.
- The audit trail is hash-chained: every event stores the previous hash; the web client can verify it
  and the server writes JSONL. Tampering is detectable.
- Confidence is disclosed on every finding and in every PDF.

## Security / tenancy

`security.TenantStore` scopes writes to `<root>/<tenant>/` and rejects path escapes and invalid tenant
IDs. The demo is single-tenant, but the layout is multi-tenant from day one. The privacy checklist is
engineered into the Method page. PII redaction is available for exports.

## Testing

- `tests/` covers geometry, tiling, detection, ranking, assessment, exports, audit, connectors,
  monitoring, NPU, tenancy, models, packs, data-pack contract and the API.
- `web` build runs `tsc -b` then Vite.
- The stage flow is exercised through a browser script during development (open → scrub → inspect →
  reject → vote → assign → reveal → field order).

## Production swaps

| Demo | Production |
|---|---|
| simulated raster | licensed Sentinel-2 / commercial / drone GeoTIFF |
| procedural context | OSM / PostGIS / ArcGIS / claims extract |
| precomputed findings | fine-tuned vision backbone + NPU/GPU inference |
| client-side persistence | API + database + SSO |
| synthetic pilot numbers | adjuster-confirmed outcomes |


## Proactive subsystem

The Watch tab is backed by `georesponse/proactive/`:

```
scope/plan ─► scheduler ─► acquisition ─► baseline ─► alert ─► incident ─► route ─► notify ─► human
                  │                           │                          │
              budget/cost                 confirmation                outbox/SLA
              de-dupe/retry               suppression                 audit/gates
```

- **State:** SQLite WAL with JSON rows; a PostgreSQL schema is in `deploy/sql/postgres_schema.sql`.
- **Scheduler:** cadence, idempotency, overlap de-dupe, commercial approval, budget, retries,
  readiness, calendar, air-gap import, cost anomaly.
- **Baseline:** seasonal statistics, trend/abruptness, multi-temporal and optical/SAR confirmation,
  adaptive thresholds, construction/vegetation/erosion detectors, suppression, drift, backtest,
  calibration and analyst feedback.
- **Anticipation:** forecast ingest, pre-event watchlist, lead time, uncertainty, tasking trigger,
  seasonal calendar, heatmap, scenario simulation.
- **Alerts:** schema, urgency, dedupe, incident grouping, state machine, routing, SLA, bulk actions,
  why panel, handoff, fatigue budget, digest, mobile card.
- **Notifications:** email/Slack/Teams/SMS/pager/HMAC webhook, quiet hours, least privilege, outbox
  retries, dead letters.
- **Governance:** model registry/rollback, explainability, false-alarm cost, overrides, precision,
  privacy, tenant keys, kill switch, rate limits, on-call, validation gate, non-goals.
- **Ops:** quotas, secrets vault, job queue, object store, backup/restore drill, load test,
  blue/green, Postgres mirror.

The UI (`Watch.tsx`, `WatchMap.tsx`) is local-first and reads `data/proactive.json`. The API exposes
the same lifecycle at `/api/watch/*`.
