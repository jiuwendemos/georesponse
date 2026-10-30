"""Create the example scope and ingest two observations into a running API.

Usage:
    python examples/workspace-example/run_api_example.py --base http://127.0.0.1:8010

The API must be running. The first observation establishes the baseline; the
second creates the alert. Nothing is approved or dispatched automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    args = parser.parse_args()

    scope_body = json.loads((ROOT / "scope.json").read_text(encoding="utf-8"))
    observations = json.loads((ROOT / "observations.json").read_text(encoding="utf-8"))

    with httpx.Client(base_url=args.base, timeout=60) as client:
        health = client.get("/api/health")
        print("health", health.status_code, health.json().get("status"))
        scope = client.post("/api/watch/scopes", json=scope_body)
        scope.raise_for_status()
        scope_id = scope.json()["id"]
        print("scope", scope_id, scope.json()["name"])

        baseline = json.loads((ROOT / "baseline.json").read_text(encoding="utf-8"))
        seeded = client.post(f"/api/watch/scopes/{scope_id}/baseline", json=baseline)
        seeded.raise_for_status()
        print("baseline", seeded.json()["mean"], "from", len(seeded.json()["values"]), "values")

        for index, entry in enumerate(observations, 1):
            body = {
                "scopeId": scope_id,
                "modelVersion": entry.get("modelVersion", "gr-changenet-example"),
                "observation": entry["observation"],
            }
            response = client.post("/api/watch/observations", json=body)
            response.raise_for_status()
            result = response.json()
            print(f"observation {index}: {result.get('status')}", (result.get("alert") or {}).get("id", ""))

        overview = client.get("/api/watch/overview", params={"tenant": scope_body.get("tenant", "demo")})
        if overview.status_code == 200:
            payload = overview.json()
            print("alerts", len(payload.get("alerts", [])), "scopes", len(payload.get("scopes", [])))
            print("open the app with the API running to see the live Watch inbox")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
