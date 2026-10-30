# Deployment notes

## Docker

```bash
docker compose up --build
# http://127.0.0.1:8000/
```

The image builds the SPA, then serves it from FastAPI. The API is at `/api/*`; OpenAPI docs at `/docs`.

## GitHub Pages

`.github/workflows/pages.yml` builds `web/` and deploys `web/dist`. Enable **Pages → GitHub Actions** in
the repository settings once.

## Air-gapped

```bash
docker save georesponse-georesponse -o georesponse.tar
# copy tarball + data volume to the customer host
docker load -i georesponse.tar
```

Run with `--network none`; the stage pack is fully local.

## NPU profile

`web/public/data/npu.json` describes the reference device, batch size and throughput. The broker is in
`georesponse/npu.py`; register the pinned model version before submitting jobs.

## Tenant data

Mount a volume at `/srv/georesponse/runtime` and keep one directory per tenant. The `TenantStore` rejects
path escapes. Back up the audit JSONL and the assessments; raw imagery follows the customer's retention
clock.


## Production wiring

Copy `.env.example` to `.env`, fill the credentials you have, then:

```bash
docker compose up --build
```

This starts Postgres, Redis, MinIO, the API and the proactive worker. `GET /api/watch/production/doctor`
reports what is live without printing secrets. The full checklist is in
[docs/PRODUCTION_WIRING.md](../docs/PRODUCTION_WIRING.md).

For a single-box local run without Postgres/Redis/MinIO, keep the default SQLite store and run:

```bash
py -m georesponse.cli serve
py -m georesponse.production.worker
```
