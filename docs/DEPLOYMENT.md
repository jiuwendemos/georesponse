# Deployment

## Option A — GitHub Pages (live demo)

The repository ships `.github/workflows/pages.yml`. On every push to `main` it:

1. installs the web dependencies,
2. runs `npm run build` (with `base: './'`, so the app works under `/georesponse/`),
3. uploads `web/dist` and deploys it.

**Live URL:** https://jiuwendemos.github.io/georesponse/

The data pack is committed under `web/public/data/`, so Pages needs no Python build step. Regenerate it
locally and commit the result when the scenario changes.

## Option B — Docker / private host

```bash
docker compose up --build
# http://127.0.0.1:8000/
```

The image builds the web app and serves it from the FastAPI process. API docs: `/docs`.

The container needs no outbound network at runtime. Mount a tenant data volume for the pilot:

```yaml
volumes:
  - georesponse-data:/srv/georesponse/runtime
```

## Option C — on-site / air-gapped

1. Copy the image and the data pack.
2. Run with `--network none` after deployment; the app is static-first.
3. Put the optional NPU broker beside the API; register the pinned model version.
4. Point the audit volume at the customer's encrypted storage.

No imagery leaves the customer network after delivery.

## Environment

| Variable | Purpose |
|---|---|
| `GEORESPONSE_DATA_DIR` | override the data directory (default `web/public/data`) |
| `GEORESPONSE_AUDIT` | audit JSONL path (default `runtime/audit.jsonl`) |

The demo has no secrets. Commercial connectors are dry-run and read credentials only when a real
deployment enables them.

## Offline pack

In the app: **Booth → Offline pack** or **Pilot → Save offline pack**. This pre-caches the scenario JSON,
basemap and every evidence image. The service worker serves the cache when offline. For a USB stick,
serve `web/dist` with any static server.

## Health checks

- `GET /api/health` — status, model version, scenario count.
- `py -m georesponse.cli verify` — validate the audit chain.
- `py -m georesponse.cli connectors` — list imagery connector state.
- `py -m georesponse.cli report` — pilot summary.

## Rollback

The data pack and app are immutable build artefacts. Roll back by redeploying the previous commit; the
audit log and tenant data are separate volumes.


## Proactive worker

The proactive loop is a deterministic tick, so it can run from cron, a container worker or an
air-gapped scheduler:

```bash
python -c "from georesponse.proactive.api import engine, store; import json; print(json.dumps(engine.run_tick(tenant='demo', forecasts=store.list_forecasts()), indent=2))"
```

Run it every 15 minutes. The scheduler is idempotent per scope/cadence/source, so duplicate ticks do
not duplicate acquisitions.

## Proactive persistence

- Demo: SQLite WAL (`runtime/proactive.db`).
- Production: PostgreSQL schema in `deploy/sql/postgres_schema.sql`; `PostgresMirror` validates sync.
- Imagery/evidence: `LocalObjectStore` (`runtime/objects`) with lifecycle deletion; swap for S3/GCS.
- Queue: `JobQueue` in SQLite with claim/complete/fail-backoff/replay/dead-letter; swap for Redis/SQS.
- Keys: per-tenant Fernet keys in `runtime/keys` (0600); swap for KMS/Vault.
- Audit: hash-chained table; export with the API.

## Proactive runbook

```bash
python -m georesponse.cli load-test --scopes 1000 --alerts 10
python -m georesponse.cli drill
python -m georesponse.cli airgap --scope scope-ahr-corridor --folder ./incoming
```

Kill switch: `POST /api/watch/kill-switch?active=true`; it stops acquisition, alerts and
notifications for the tenant. Re-enable with `active=false`.
