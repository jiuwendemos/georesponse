"""Production scheduler/notification worker.

Runs the deterministic proactive tick on an interval.  Safe to run as one replica;
the store and scheduler are idempotent.  Sends notifications through the live
transports when configured, otherwise the outbox records failed deliveries.

Every tick writes `runtime/worker-heartbeat.json` atomically. The health endpoint
reads it, so a silent worker is visible without log access.
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from ..proactive.engine import ProactiveEngine
from .config import get_settings
from .store_pg import build_store

ROOT = Path(__file__).resolve().parents[2]
HEARTBEAT = ROOT / "runtime" / "worker-heartbeat.json"


def _write_heartbeat(payload: dict) -> None:
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    temporary = HEARTBEAT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, default=str), encoding="utf-8")
    temporary.replace(HEARTBEAT)


def run_once(tenant: str | None = None) -> dict:
    settings = get_settings()
    store = build_store(settings.platform.postgres_dsn)
    engine = ProactiveEngine(store, live_channels=settings.mode == "production")
    started = time.perf_counter()
    status = "ok"
    error = None
    try:
        result = engine.run_tick(tenant=tenant or settings.platform.tenant, forecasts=store.list_forecasts())
        return result
    except Exception as exc:  # noqa: BLE001 - recorded then re-raised
        status = "error"
        error = str(exc)
        raise
    finally:
        _write_heartbeat({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tenant": tenant or settings.platform.tenant,
            "status": status,
            "error": error,
            "durationMs": round((time.perf_counter() - started) * 1000, 1),
        })
        store.close()


def main() -> None:
    settings = get_settings()
    interval = int(os.getenv("GEORESPONSE_TICK_SECONDS", "900"))
    tenant = settings.platform.tenant
    running = True

    def stop(*_args) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            result = run_once(tenant)
            print({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tenant": tenant,
                "scheduled": len(result.get("scheduled", {}).get("planned", [])),
                "sla": len(result.get("slaBreaches", [])),
            }, flush=True)
        except Exception as exc:  # noqa: BLE001 - worker must keep running
            print({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "error": str(exc),
            }, flush=True)
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
