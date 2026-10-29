# Data rights & provenance

## What the demo uses

| Layer | Status | Attribution |
|---|---|---|
| Basemap / scenes / evidence | **Simulated**, generated deterministically | “© Copernicus Sentinel data (simulated demo pack)” |
| OSM-shaped context | Simulated shapes in the demo; production uses OSM | “© OpenStreetMap contributors” (ODbL) |
| Event structure | Based on the July 2021 Ahr valley flood | Public event; no copyrighted imagery copied |
| Commercial imagery | Not included | Licence required even for a demo |

The app labels the pack **simulated** in the provenance panel, the Method page, the booth, the field
order and every PDF. It is never presented as an operational capture.

## Production sources

- **Sentinel-2 L2A** — free and open; attribution required. `SentinelConnector` targets the Copernicus
  STAC catalogue.
- **Sentinel-1 SAR** — free and open; attribution required. `SentinelSARConnector`.
- **Copernicus EMS** — published maps have their own terms; verify before using a published map as the
  hero image.
- **OpenStreetMap** — ODbL; display “© OpenStreetMap contributors”. Derivative databases share alike.
- **Commercial imagery** (Planet, Maxar, Airbus, ICEYE, Capella) — a licence is required for any use,
  including a public stage. Do not assume a trial covers a conference.
- **Customer drone orthophoto / LAS** — governed by the customer's data-processing agreement.

## Provenance sheet

Every assessment stores and displays:

- imagery source and acquisition time,
- whether the pack is simulated,
- model name and version (pinned),
- cloud screen and confidence,
- analyst, review decision and corrections,
- the audit-chain hash.

The JSONL audit trail is append-only and hash-chained. `py -m georesponse.cli verify` checks it.

## Retention & deletion

Pilots set a retention clock per event. Raw imagery is deleted after the claim decision plus the legal
minimum. The audit summary and assessment remain for the contractual period. The customer can export
everything as GeoJSON, PDF and JSON.

## Ethics

- No facial recognition, no live video surveillance.
- Residential imagery is cropped to the insured property footprint for inference.
- No automated decision about people or property; a human signs.
- A wrong map can cost money or lives — the app says so, in the report and on stage.
