"""Minimal observability primitives for the proactive loop."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

_LOGGER = logging.getLogger("georesponse.proactive")


class Metrics:
    def __init__(self) -> None:
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.timings: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def observe(self, name: str, milliseconds: float) -> None:
        self.timings[name].append(round(milliseconds, 2))

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, (time.perf_counter() - start) * 1000)

    def snapshot(self) -> dict:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timings": {key: {"count": len(values), "avgMs": round(sum(values) / len(values), 2), "maxMs": max(values)} for key, values in self.timings.items()},
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


METRICS = Metrics()


def structured_log(event: str, **fields) -> dict:
    record = {"event": event, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields}
    _LOGGER.info(json.dumps(record, sort_keys=True, default=str))
    return record


def new_trace_id() -> str:
    return uuid.uuid4().hex


def metrics_snapshot() -> dict:
    return METRICS.snapshot()
