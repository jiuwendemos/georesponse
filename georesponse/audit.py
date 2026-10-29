"""Append-only, hash-chained audit trail.

Each event includes the hash of the previous event, so edits or deletions are
detectable.  The client mirrors the same structure in localStorage; the server
writes the authoritative JSONL file.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_event(event: dict) -> str:
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def append_event(path: str | Path, event: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = GENESIS
    if path.exists() and path.stat().st_size:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            previous = json.loads(lines[-1])["hash"]
    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "imagery": event.get("imagery"),
        "modelVersion": event.get("modelVersion"),
        "analyst": event.get("analyst"),
        "action": event["action"],
        "siteId": event.get("siteId"),
        "detail": event.get("detail", {}),
        "prev": previous,
    }
    record["hash"] = hash_event(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_events(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_chain(events: Iterable[dict]) -> tuple[bool, str]:
    previous = GENESIS
    for index, event in enumerate(events):
        if event.get("prev") != previous:
            return False, f"event {index}: broken prev link"
        if hash_event(event) != event.get("hash"):
            return False, f"event {index}: hash mismatch"
        previous = event["hash"]
    return True, "chain intact"


def audit_csv(events: list[dict]) -> str:
    lines = ["at,action,siteId,analyst,modelVersion,hash"]
    for e in events:
        lines.append(
            ",".join(
                '"' + str(e.get(k, "")).replace('"', '""') + '"'
                for k in ("at", "action", "siteId", "analyst", "modelVersion", "hash")
            )
        )
    return "\n".join(lines)
