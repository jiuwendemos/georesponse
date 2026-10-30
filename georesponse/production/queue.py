"""Redis-backed job queue with the same contract as the SQLite queue."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .config import PlatformSettings, get_settings


class QueueUnavailable(RuntimeError):
    pass


class RedisJobQueue:
    def __init__(self, settings: PlatformSettings | None = None, *, prefix: str = "georesponse:jobs") -> None:
        self.settings = settings or get_settings().platform
        if not self.settings.redis_url:
            raise QueueUnavailable("Redis is not configured")
        import redis

        self.client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True)
        self.prefix = prefix

    def _queued(self, queue: str) -> str:
        return f"{self.prefix}:{queue}:queued"

    def _running(self, queue: str) -> str:
        return f"{self.prefix}:{queue}:running"

    def _job(self, job_id: str) -> str:
        return f"{self.prefix}:job:{job_id}"

    def enqueue(self, queue: str, payload: dict, *, available_at: float | None = None) -> str:
        job_id = f"job-{int(time.time()*1000)}-{time.perf_counter_ns() % 100000}"
        job = {"id": job_id, "queue": queue, "payload": json.dumps(payload), "attempts": 0, "status": "queued", "available_at": available_at or time.time()}
        self.client.hset(self._job(job_id), mapping={k: str(v) for k, v in job.items()})
        self.client.zadd(self._queued(queue), {job_id: float(job["available_at"])})
        return job_id

    def claim(self, queue: str, *, limit: int = 1) -> list[dict]:
        now = time.time()
        ids = self.client.zrangebyscore(self._queued(queue), "-inf", now, start=0, num=limit)
        claimed = []
        for job_id in ids:
            if not self.client.zrem(self._queued(queue), job_id):
                continue
            self.client.hset(self._job(job_id), mapping={"status": "running", "attempts": str(int(self.client.hget(self._job(job_id), "attempts") or 0) + 1)})
            job = self.client.hgetall(self._job(job_id))
            job["payload"] = json.loads(job.get("payload", "{}"))
            self.client.rpush(self._running(queue), job_id)
            claimed.append(job)
        return claimed

    def complete(self, job_id: str) -> None:
        self.client.hset(self._job(job_id), "status", "done")

    def fail(self, job_id: str, error: str, *, max_attempts: int = 4) -> str:
        job = self.client.hgetall(self._job(job_id))
        attempts = int(job.get("attempts", 0))
        status = "dead" if attempts >= max_attempts else "queued"
        self.client.hset(self._job(job_id), mapping={"status": status, "error": error})
        if status == "queued":
            self.client.zadd(self._queued(job["queue"]), {job_id: time.time() + 2**attempts})
        return status

    def replay(self, job_id: str) -> None:
        job = self.client.hgetall(self._job(job_id))
        self.client.hset(self._job(job_id), mapping={"status": "queued", "attempts": "0", "error": ""})
        self.client.zadd(self._queued(job["queue"]), {job_id: time.time()})

    def stats(self, queue: str | None = None) -> dict:
        queues = [queue] if queue else [key.split(":")[-2] for key in self.client.scan_iter(f"{self.prefix}:*:queued")]
        return {"queues": {name: self.client.zcard(self._queued(name)) for name in queues}, "backend": "redis"}


def health(settings: PlatformSettings | None = None) -> dict:
    settings = settings or get_settings().platform
    if not settings.redis_url:
        return {"configured": False, "ok": False, "detail": "set GEORESPONSE_REDIS_URL"}
    try:
        queue = RedisJobQueue(settings)
        queue.client.ping()
        return {"configured": True, "ok": True, "url": settings.redis_url.split("@")[-1]}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "ok": False, "detail": str(exc)}
