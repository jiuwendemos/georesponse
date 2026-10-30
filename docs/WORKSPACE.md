# Workspace — your data vs the demo pack

GeoResponse has two data sources, switchable at any time:

| Source | What you see | Where it lives |
|---|---|---|
| **Demo pack** | 3 scenarios, 24 alerts, 6 scopes | Committed JSON in `web/public/data` |
| **My workspace** | Only your imported sites | This browser (`localStorage`) until you connect a backend |

Switch in **Settings → Data source**, or open the **Workspace** tab directly.

## First run

- Default is **Demo pack**, so a manager demo always has content.
- Choose **My workspace** to get an empty workspace with an import CTA.
- The demo pack stays one click away. Nothing is deleted when you switch.

## Add your own sites (UI)

1. Open **Workspace**.
2. Use **Load example case** to see a complete example, or **Import CSV / GeoJSON**.
3. Required fields: `name`, `lat`, `lon` (WGS84).
4. Optional: `id`, `severity`, `confidence`, `value_eur`, `population`, `access`, `notes`.
5. Review the preview, import, then edit any row on the right.
6. Export CSV or GeoJSON when finished.

Supported GeoJSON: a `FeatureCollection` of `Point` features. Other geometries are
skipped with a message.

## Work with the example

- Files: [`examples/workspace-example`](../examples/workspace-example)
- `sites.csv` / `sites.geojson` — import in the Workspace tab.
- `scope.json` + `observations.json` — the proactive API path.
- `run_api_example.py` — creates the scope and ingests two observations.

```powershell
py -m georesponse.cli serve --port 8010
py examples/workspace-example/run_api_example.py --base http://127.0.0.1:8010
```

The first observation sets the baseline; the second creates an alert. Open the
app with the API running and Watch reads the live store.

## What the Workspace does not do yet

- It does not upload imagery. The proactive/imagery path is CLI/API.
- It does not create a full scenario timeline. Stage/Analyst/Pilot are demo
  scenarios; in workspace mode they show a gate instead of demo data.
- It does not sync across devices. Data is in this browser until a backend is
  connected.

## Data model and guarantees

- Imported sites never overwrite the demo pack.
- Deleting a site removes it from this browser only.
- IDs are the merge key: importing the same ID replaces that row.
- Coordinates are validated; invalid rows are rejected with a message.
- The source badge on the workspace says whether you are in demo or workspace mode.

See [PHASE7_STATUS.md](PHASE7_STATUS.md) for what remains before customer imports
are production-grade (server-side storage, tenant isolation, audit on import).
