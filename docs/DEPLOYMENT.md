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
