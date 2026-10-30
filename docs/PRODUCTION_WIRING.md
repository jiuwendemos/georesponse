# Production wiring

This page separates three things that used to be blurred:

1. **Real and verified in this workspace.**
2. **Real code that needs operator credentials or hardware.**
3. **Sample data that must be replaced with customer data.**

No secret is printed by the app or the doctor.

## 1. Real and verified here

| Layer | Implementation | Evidence |
|---|---|---|
| Sentinel-2 imagery | Earth Search STAC → Sentinel-2 L2A COG → windowed rasterio read | Real Ahr pair `S2B_32ULB_20210703_0_L2A` / `S2A_32ULB_20210718_0_L2A`; Eifel and Cologne pairs also cached |
| Image metadata | STAC item ID, datetime, cloud, platform, CRS, source URL, attribution | `web/public/data/real/*/*.json` |
| ONNX inference | `models/damage-head.onnx` executed by ONNX Runtime | `OnnxDamageModel.health()` reports providers/device; `infer` CLI |
| LLM agent | OpenAI-compatible tool-calling loop with 7 grounded tools | Live smoke against the configured model: tool calls + proposal, no mutation |
| openjiuwen agent | `create_deep_agent`, `ModelClientConfig`, `Runner`, `@tool` | Live smoke in the jiuwenswarm environment returned a 2.5k-char grounded briefing |
| Agent safety | Reads execute; writes return proposals; refusal for auto-approval/auto-dispatch | `production/agent.py`, `production/openjiuwen_runtime.py`, tests |
| Notification transports | SMTP, Slack, Teams, Twilio, PagerDuty, HMAC webhook | Mock HTTP transport tests; real code raises when unconfigured |
| Integrations | Jira, ServiceNow, Guidewire, Duck Creek, Maximo, SAP, ArcGIS, SIEM | Mock HTTP tests; live HTTP adapters |
| Auth | API key or OIDC bearer (RS256 / JWKS) | `production/auth.py` |
| State | SQLite for local; PostgreSQL store implementation + production schema | `production/store_pg.py`, `deploy/sql/postgres_schema.sql` |
| Queue | SQLite job queue or Redis queue | `proactive/ops.py`, `production/queue.py` |
| Object storage | Local content store or S3/MinIO | `production/storage.py` |
| Worker | Deterministic tick loop, live channels in production mode | `production/worker.py`, `docker-compose.yml` |
| Doctor | No-secret readiness report | `georesponse doctor` / `GET /api/watch/production/doctor` |
| Bundle/lazy load | Watch/Analyst/Pilot/Booth/Method split; jsPDF on demand | `npm run budget` → 112 KB gzip initial |

## 2. Real code that needs operator credentials or hardware

These are wired but cannot be proven live from this machine:

- **Commercial imagery credentials** — Planet, Maxar, Airbus, ICEYE, Capella; SFTP.
- **Notification channels** — SMTP host, Slack/Teams webhook, Twilio, PagerDuty.
- **Enterprise systems** — Jira, ServiceNow, Guidewire, Duck Creek, Maximo, SAP, ArcGIS, SIEM.
- **PostgreSQL/Redis/MinIO** — Docker daemon was not running here; schema, adapters and compose file are present.
- **NPU** — ONNX Runtime has only CPU/Azure providers in this environment. The code prefers
  `CANNExecutionProvider` (Ascend), OpenVINO NPU, QNN or CoreML when installed. Hardware acceptance still needs the target box.
- **Production vision model** — the bundled ONNX model is a real damage-likelihood head, not a trained roof-damage CNN. Replace `models/damage-head.onnx` with the customer-trained model; the runtime does not change.

Run:

```powershell
py -m georesponse.cli doctor
```

A red optional check disables only that channel. A red required check means the live path is not ready.

## 3. Sample data that must be replaced

- Site names, coordinates, asset values, population and the 18-site ranking.
- Flood/burn timeline polygons (reconstructed stage timeline).
- Proactive scopes, alerts, incidents, forecasts and pilot metrics.
- Insurer policies and claims.

The real Sentinel pixels do **not** make the asset graph real. Replace the sample pack with the
customer's assets, claims and adjuster-confirmed labels before an operational decision.

## Agent wiring

```powershell
# OpenAI-compatible backend
py -m georesponse.cli agent --message "Brief me on the open alerts and propose a safe action."

# openjiuwen backend (run in the jiuwenswarm venv)
$env:GEORESPONSE_AGENT_BACKEND = "openjiuwen"
py -m georesponse.cli agent --message "Brief me"
```

The frontend tries `/api/watch/production/agent/chat`; if the API is not present it falls back to the
deterministic local tool parser and says so. It never pretends a live model is present.

## Inference

```powershell
py -m georesponse.cli infer --before path/before.png --after path/after.png
py -m georesponse.cli doctor
```

To target an NPU, install the vendor ONNX Runtime and set:

```powershell
$env:GEORESPONSE_ONNX_PROVIDERS = "CANNExecutionProvider"
# or OpenVINOExecutionProvider / QNNExecutionProvider / CoreMLExecutionProvider
```

## Imagery

```powershell
py -m georesponse.cli fetch-imagery --scenario all
```

Sentinel-2 is free and open; attribution is mandatory. Commercial providers require a licence.

## Notifications and integrations

Copy `.env.example` to `.env`, fill the channels you have, then:

```powershell
py -m georesponse.cli doctor
docker compose up --build
```

The worker sends live notifications only when `GEORESPONSE_MODE=production`; otherwise the outbox is
local and clearly labelled. Integration endpoints return 503 when their credentials are missing.

## Cutover checklist

- [ ] `doctor` required checks green.
- [ ] Real customer imagery delivered and provenance recorded.
- [ ] Customer assets/claims loaded; sample pack removed.
- [ ] Agent model approved for the customer's data boundary.
- [ ] Notification channels tested with one real recipient.
- [ ] Each enterprise integration tested against a sandbox tenant.
- [ ] NPU acceptance run with the target model.
- [ ] Postgres/Redis/MinIO backup and restore drill.
- [ ] Legal/DPA/privacy sign-off.


> **Where the live cutover lives:** Phase 7.C in [ROADMAP.md](ROADMAP.md) is the 122-checkbox
> programme to connect openjiuwen, NPU, imagery, notifications, enterprise systems, platform,
> identity, observability and cutover for real.

## Operator insights (verified)

The proactive API now exposes the facts an operator needs between ticks:

| Endpoint | Purpose |
|---|---|
| `GET /api/watch/since?ts=` | What changed since a timestamp (alerts, incidents, notifications, closures) |
| `GET /api/watch/drift?days=14` | Per-scope alert-rate drift: emerging, silent, spike, quiet, stable |
| `GET /api/watch/notifications/analytics` | Delivery rate, dead letters and send latency by channel |
| `POST /api/watch/alerts/{id}/feedback` | useful / not_useful / wrong, stored and audited |
| `GET /api/watch/feedback/summary` | Feedback counts and useful rate |
| `GET /api/watch/production/worker/health` | Last worker heartbeat, age and stale flag |
| `POST /api/watch/scopes/{id}/pause?reason=` | Pause with an audited reason |
| `POST /api/watch/scopes/{id}/resume?reason=` | Resume with an audited reason |

The agent now validates every tool call against its schema, refuses unsafe
requests before calling a model, retries transient upstream errors with backoff
and opens a circuit after repeated failures. It reports `promptVersion` in
`/api/watch/production/agent/health`.

Tests: `tests/test_insights.py`, `tests/test_production.py`.

## Agent evaluation and audit export

```powershell
py -m georesponse.cli evaluate-agent          # guardrails + tool schemas, no model
py -m georesponse.cli evaluate-agent --live   # golden questions against the configured model
```

The live run checks expected tool calls and that read-only questions never
produce a write proposal. The offline run is part of CI.

`GET /api/audit/export` returns the hash-chained audit as
`application/x-ndjson` with `X-Audit-Verified` and `X-Audit-Message` headers.

Rate limiting is now keyed by the authenticated principal (API key or OIDC
subject) and falls back to the client address only when authentication is off.

## Imagery retention

```powershell
py -m georesponse.cli prune-imagery --days 90            # dry run
py -m georesponse.cli prune-imagery --days 90 --apply    # delete cached files
```

Only `runtime/imagery` is pruned. Committed demo packs and customer source
imagery are never touched by this command. S3 lifecycle rules are available in
`production/storage.py` for object stores.
