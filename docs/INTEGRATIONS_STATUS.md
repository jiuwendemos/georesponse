# External integrations — status and usage

As of 2026-10-30. Verified with `georesponse doctor`, live agent calls, a live
STAC query, ONNX inference, and the API health endpoints.

Status legend: **Live** = reachable and exercised here · **Wired** = real adapter,
needs credentials/host · **Missing** = no credentials/configuration · **Blocked** =
needs hardware or customer data.

## 1. AI, agent and inference

| Service | Status | Why the app needs it | What the app does with it |
|---|---|---|---|
| **LLM (OpenAI-compatible, DeepSeek)** | **Live** | Turns a question into a grounded answer and tool plan | Tool-calling analyst agent: briefing, alert detail, coverage, proposals. Verified live against `deepseek-v4-pro`. |
| **openjiuwen runtime** | **Live in the jiuwenswarm venv; inactive on Pages** | Planning, subagents, sessions, rails and streaming | Auto-selected when its runtime loads: AgentCard, task planning, four subagents, policy rail, SSE stream, session memory. |
| **ONNX Runtime (CPU)** | **Live** | Runs the damage-likelihood head without a GPU | Scores a real Sentinel before/after pair; returns probability, change fraction, cloud, device. |
| **NPU provider (CANN / OpenVINO / QNN)** | **Blocked** | Faster inference on customer hardware | Provider precedence exists; only CPU and Azure providers are available here. No NPU acceptance run. |
| **Production vision CNN** | **Missing** | Accuracy on real roof/asset damage | The current `damage-head.onnx` is a real but small head, not a trained production CNN. |

## 2. Imagery and geospatial

| Service | Status | Why the app needs it | What the app does with it |
|---|---|---|---|
| **Sentinel-2 STAC (Earth Search)** | **Live** | Finds cloud-free before/after scenes | Searches by bbox/date/cloud, reads a windowed COG, caches PNGs and stores STAC item id, datetime, CRS, source and attribution. |
| **Sentinel-1 SAR** | **Wired (detection logic), no live fetch** | Reliable change detection under cloud | Fusion logic accepts SAR confidence; the example observations include a SAR channel. No live SAR download path is exercised. |
| **Planet / Maxar / Airbus / ICEYE / Capella** | **Missing** | Higher resolution and faster revisit | Connector shells and licence fields exist; no credentials, no live scene, no per-scene licence check. |
| **Customer SFTP / drone orthophoto** | **Missing** | Customer-owned imagery and LAS/GeoTIFF | `import_airgap` can read a local folder; no customer endpoint or UI upload. |
| **OSM tiles / vector basemap** | **Not used at runtime** | Street context | The app draws a custom SVG map over a Sentinel basemap and shows OSM attribution. It does not call a live OSM tile service. |

## 3. Notifications

| Service | Status | Why the app needs it | What the app does with it |
|---|---|---|---|
| **SMTP email** | **Missing** | Send alert digests and assignments | `send_email` via `smtplib`; raises when `SMTP_HOST` is absent. |
| **Slack** | **Missing** | Team channel alerts | Signed JSON post to a webhook; raises when unset. |
| **Microsoft Teams** | **Missing** | Enterprise channel alerts | Adaptive-card webhook post; raises when unset. |
| **Twilio SMS** | **Missing** | Reach a field responder without the app | REST message create; raises when SID/token/from are absent. |
| **PagerDuty** | **Missing** | Wake an on-call operator for red alerts | Events API v2 trigger; raises when the routing key is absent. |
| **Generic webhook** | **Missing** | Customer middleware / automation | HMAC-signed JSON post; raises when the URL is absent. |
| **Push notifications** | **Missing** | Mobile return trigger | No push service; the PWA has an offline shell, not a push backend. |

## 4. Enterprise systems

| Service | Status | Why the app needs it | What the app does with it |
|---|---|---|---|
| **Jira** | **Missing** | Track inspection and remediation work | Creates an issue from an alert (REST v3), draft-only. |
| **ServiceNow** | **Missing** | Enterprise incident workflow | Creates an incident in the incident table. |
| **Guidewire** | **Missing** | Claims system of record | Creates a claim draft from an assessment. |
| **Duck Creek** | **Missing** | Claims system of record | Creates a claim draft from an assessment. |
| **IBM Maximo** | **Missing** | Asset maintenance work order | Creates an inspection/work-order request. |
| **SAP** | **Missing** | Enterprise asset/maintenance | Creates an inspection request via HTTP. |
| **ArcGIS** | **Missing** | GIS feature layer for spatial teams | Pushes alert features to a FeatureServer layer. |
| **SIEM (Splunk HEC)** | **Missing** | Security/audit event stream | Sends alert events to an HTTP Event Collector. |

All enterprise calls are **draft-only**: a human approves before anything is sent.

## 5. Platform, identity and operations

| Service | Status | Why the app needs it | What the app does with it |
|---|---|---|---|
| **PostgreSQL** | **Missing / not running** | Durable multi-tenant operational store | `PostgresStore` mirrors scopes, baselines, incidents, alerts, audit; SQLite is used locally. |
| **Redis** | **Missing / not running** | Durable job queue and retries | `RedisJobQueue` for scheduler/notification jobs; SQLite queue is the fallback. |
| **S3 / MinIO** | **Missing / not running** | Evidence, exports and imagery objects | `S3ObjectStore` with presigned URLs and lifecycle; local object store otherwise. |
| **OIDC / customer IdP** | **Missing** | Real user identity and tenant claims | `authenticate` supports API key or RS256/JWKS; neither is configured. |
| **API key auth** | **Wired, no key** | Protect the API | Middleware returns 401 when configured; currently `authConfigured: false`. |
| **Docker / Compose** | **Not running here** | One-command Postgres/Redis/MinIO/API/worker | Compose file exists; the Docker daemon is unavailable on this machine. |
| **OTLP / observability** | **Missing** | Customer traces, metrics and logs | Audit and worker heartbeats exist; no OTLP exporter is configured. |
| **GitHub Pages** | **Live (static)** | Public demo | Serves the SPA and real Sentinel images; no API, worker or database. |

## 6. What runs where

| Environment | What is actually live |
|---|---|
| Public Pages | Static SPA, committed demo pack, real Sentinel images, local tool parser only |
| Local API in `jiuwenswarm` venv | LLM agent, openjiuwen (auto), ONNX CPU, STAC imagery, Watch/audit/SQLite |
| Production target | Everything above plus Postgres/Redis/S3/auth/worker — **not deployed** |

## 7. How to check

```powershell
py -m georesponse.cli doctor
py -m georesponse.cli evaluate-agent
```

```text
GET /api/watch/production/doctor
GET /api/watch/production/agent/health
GET /api/watch/production/inference/health
GET /api/watch/production/notifications/channels
GET /api/watch/production/integrations/status
```

A red optional check disables only that channel. A red required check means the
live path is not ready.

## 8. What this means for a customer case

- You can import your own **sites** today in the Workspace tab (CSV/GeoJSON).
- You can run a real **proactive case** with the API: create a scope and ingest
  observations; alerts, evidence, audit and proposals are real.
- You **cannot** yet deliver notifications, create Jira/ServiceNow/claims records,
  store data in Postgres/Redis/S3, authenticate users via your IdP or run on an NPU
  without those credentials/hardware.
- The public site remains a demo. Live services run only where the API/worker are
  hosted.

See [PRODUCTION_WIRING.md](PRODUCTION_WIRING.md) and
[PHASE7_STATUS.md](PHASE7_STATUS.md) for the cutover checklist.
