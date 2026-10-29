"""Optional NPU broker.

On-site inference wants batching, a queue and model pinning without exposing the
network.  This module is a small, testable broker; the production version talks
to the vendor runtime (CANN/Ascend, OpenVINO, ONNX Runtime) behind the same
``infer`` interface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from . import MODEL_VERSION


@dataclass
class ModelRecord:
    name: str
    version: str
    path: str
    device: str = "npu"
    loaded: bool = False
    runs: int = 0


@dataclass
class InferenceJob:
    id: str
    tiles: int
    model: str
    priority: int = 5
    status: str = "queued"
    result: dict | None = None
    error: str | None = None


class NPUBroker:
    def __init__(self, *, batch_size: int = 8) -> None:
        self.batch_size = batch_size
        self.models: dict[str, ModelRecord] = {}
        self.jobs: list[InferenceJob] = []
        self.audit: list[dict] = []

    def register_model(self, name: str, path: str, version: str = MODEL_VERSION, device: str = "npu") -> ModelRecord:
        record = ModelRecord(name=name, version=version, path=path, device=device, loaded=True)
        self.models[name] = record
        self.audit.append({"event": "model.registered", "name": name, "version": version, "device": device})
        return record

    def submit(self, job: InferenceJob) -> InferenceJob:
        if job.model not in self.models:
            raise KeyError(f"model not registered: {job.model}")
        self.jobs.append(job)
        self.jobs.sort(key=lambda j: (j.priority, j.id))
        return job

    def run(self, runner: Callable[[InferenceJob], dict], limit: int = 1) -> list[InferenceJob]:
        processed: list[InferenceJob] = []
        for job in [j for j in self.jobs if j.status == "queued"][:limit]:
            job.status = "running"
            started = time.perf_counter()
            try:
                job.result = runner(job)
                job.status = "done"
                self.models[job.model].runs += job.tiles
            except Exception as exc:  # pragma: no cover - defensive
                job.status = "failed"
                job.error = str(exc)
            job.result = {**(job.result or {}), "elapsedMs": round((time.perf_counter() - started) * 1000, 2)}
            self.audit.append({"event": "job.finished", "id": job.id, "status": job.status})
            processed.append(job)
        return processed

    def benchmark(self, tiles: int = 64, ms_per_tile: float = 28.0) -> dict:
        batches = (tiles + self.batch_size - 1) // self.batch_size
        total_ms = tiles * ms_per_tile
        return {
            "device": "npu",
            "tiles": tiles,
            "batchSize": self.batch_size,
            "batches": batches,
            "msPerTile": ms_per_tile,
            "totalSeconds": round(total_ms / 1000, 1),
            "throughputTilesPerMinute": round(60_000 / ms_per_tile),
            "model": MODEL_VERSION,
        }

    def status(self) -> dict:
        return {
            "models": {name: record.__dict__ for name, record in self.models.items()},
            "queued": sum(1 for j in self.jobs if j.status == "queued"),
            "done": sum(1 for j in self.jobs if j.status == "done"),
            "failed": sum(1 for j in self.jobs if j.status == "failed"),
        }


def plan_batches(tiles: Iterable[dict], batch_size: int = 8) -> list[list[dict]]:
    batch: list[dict] = []
    out: list[list[dict]] = []
    for tile in tiles:
        batch.append(tile)
        if len(batch) >= batch_size:
            out.append(batch)
            batch = []
    if batch:
        out.append(batch)
    return out
