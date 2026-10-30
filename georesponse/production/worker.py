"""Production scheduler/notification worker.

Runs the deterministic proactive tick on an interval.  Safe to run as one replica;
the store and scheduler are idempotent.  Sends notifications through the live
transports when configured, otherwise the outbox records failed deliveries.
"""

from __future__ import annotations

import signal
import time
from datetime import datetime, timezone

from ..proactive.engine import ProactiveEngine
from .config import get_settings
from .store_pg import build_store


def run_once(tenant: str | None = None) -> dict:
    settings = get_settings()
    store = build_store(settings.platform.postgres_dsn)
    engine = ProactiveEngine(store, live_channels=settings.mode == "production")
    try:
        return engine.run_tick(tenant=tenant or settings.platform.tenant, forecasts=store.list_forecasts())
    finally:
        store.close()


def main() -> None:
    settings = get_settings()
    interval = int(__import__("os").getenv("GEORESPONSE_TICK_SECONDS", "900"))
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
            print({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tenant": tenant, "scheduled": len(result.get("scheduled", {}).get("planned", [])), "sla": len(result.get("slaBreaches", []))}, flush=True)
        except Exception as exc:  # noqa: BLE001 - worker must keep running
            print({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": str(exc)}, flush=True)
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
