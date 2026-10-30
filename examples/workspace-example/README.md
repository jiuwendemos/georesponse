# Example workspace case — Ahr supply corridor

This folder is a **worked example**, not customer data. It gives you real files
to upload, the exact columns to fill, and two ways to work with the case:

1. **Workspace (no backend):** import `sites.csv` or `sites.geojson` in the app
   and edit/analyse the sites.
2. **Proactive API (with backend):** create a scope and ingest two observations
   so Watch produces an alert with evidence.

Place names and coordinates are real-ish (Ahr valley). Site values, confidence,
severity and labels are **illustrative**. The Sentinel-2 evidence files are real
and already committed under `web/public/data/real/ahr-2021-flood/`.

## Files

| File | Use |
|---|---|
| `sites.csv` | Import into **Workspace → Import CSV / GeoJSON** |
| `sites.geojson` | Same sites as a GeoJSON `FeatureCollection` of Points |
| `scope.json` | Body for `POST /api/watch/scopes` |
| `observations.json` | Two observations for `POST /api/watch/observations` |
| `run_api_example.py` | Creates the scope, ingests both observations, prints alerts |

## Option A — Workspace only (no backend)

1. Open the app → **Workspace** tab, or Settings → Data source → **My workspace**.
2. Click **Load example case** (bundled copy), or **Import CSV / GeoJSON** and
   choose `sites.csv` / `sites.geojson`.
3. You should see 6 sites, 2 red, value at risk, a map and an editable table.
4. Click a row to edit name, coordinates, severity, confidence, value, people,
   access and notes. Changes are saved in this browser.
5. Export CSV or GeoJSON when you are done.

The Workspace shows **your data only**. The synthetic demo pack remains one click
away in Settings → Data source → **Demo pack**.

## Option B — Real proactive path (API + Watch)

The API must run in an environment where openjiuwen is not required for this
path; the direct backend is enough. From the repository root:

```powershell
# 1. Start the API (SQLite is fine for the example)
py -m georesponse.cli serve --port 8010

# 2. In another terminal, create the scope and ingest the two observations
py examples/workspace-example/run_api_example.py --base http://127.0.0.1:8010
```

What happens:

1. `POST /api/watch/scopes` creates the corridor scope.
2. Observation 1 (`changeFraction=0.02`) establishes the baseline, no alert.
3. Observation 2 (`changeFraction=0.16`, optical + SAR) triggers temporal
   confirmation and creates an alert with the evidence paths.
4. Open the app with the API running; Watch reads `/api/watch/overview` and shows
   the live scope and alert instead of the committed demo pack.
5. Approve or dismiss through the proposal/alert lifecycle; nothing is applied
   automatically.

If you run `GEORESPONSE_MODE=production`, the API will not seed demo scopes. The
example still works because it creates its own scope.

## Column contract for `sites.csv`

Required:

| Column | Format | Example |
|---|---|---|
| `name` | text | `Bad Neuenahr care campus` |
| `lat` | WGS84 decimal degrees, −90…90 | `50.5450` |
| `lon` | WGS84 decimal degrees, −180…180 | `7.1000` |

Optional:

| Column | Format | Default |
|---|---|---|
| `id` | unique text; generated if missing | `S-1`, `S-2`, … |
| `severity` | `red` / `orange` / `yellow` (also `high`, `watch`, `monitor`) | `orange` |
| `confidence` | 0…1 (or 0…100, divided by 100) | `0.7` |
| `value_eur` | number, currency symbols stripped | `0` |
| `population` | integer | `0` |
| `access` | `clear`, `slow`, `restricted`, `flooded`, `blocked`, `debris` | `clear` |
| `notes` | text | empty |

Column aliases accepted: `latitude`/`longitude`, `lng`, `x`/`y`, `value`,
`people`, `note`.

### GeoJSON contract

- A `FeatureCollection`.
- Every feature must be `Point`; the first two coordinates are `[lon, lat]`.
- `properties` can carry the same fields as the CSV. `id` comes from the feature
  id or properties.
- Non-point geometries are skipped with an error message.

A minimal feature:

```json
{
  "type": "Feature",
  "id": "S-01",
  "geometry": { "type": "Point", "coordinates": [7.1, 50.545] },
  "properties": { "name": "Care campus", "severity": "red", "confidence": 0.91, "value_eur": 6200000, "population": 1800, "access": "flooded" }
}
```

## Replace this with your own case

- Export sites from your GIS or asset system as CSV (WGS84) or GeoJSON Points.
- Keep at least `name`, `lat`, `lon`.
- Use your own severity/confidence or leave the defaults and edit in the table.
- For the proactive path, replace the values in `scope.json` and
  `observations.json`. `changeFraction` is the observed change (0…1), `confidence`
  is the model confidence, `sarConfidence` is optional, and `cloud`/`shadow`/`snow`
  suppress false positives.
- Replace `evidenceBefore` / `evidenceAfter` with your own image paths or object
  keys.

## What is real and what is sample

| Layer | Status |
|---|---|
| Place names and coordinates | Realistic, approximate |
| Site values, severity, confidence, labels | **Sample** |
| Sentinel-2 before/after files | **Real**, Copernicus, committed |
| Scope/observation mechanics | **Real** API path |
| Alerts, SLA, audit, proposals | **Real** code path |

Do not use the sample values for an operational decision. Replace them with
customer data and adjuster-confirmed labels first.
