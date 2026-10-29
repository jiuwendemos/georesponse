import json

import pytest

from georesponse.proactive.models import Acquisition, MonitoringPlan, Scope, TenantPreferences
from georesponse.proactive.observability import Metrics, metrics_snapshot, structured_log
from georesponse.proactive.ops import (
    BlueGreen,
    JobQueue,
    LocalObjectStore,
    PostgresMirror,
    QuotaError,
    QuotaManager,
    SecretVault,
    batch_windows,
    load_test,
    replay,
    run_airgap,
    backup_restore_drill,
)
from georesponse.proactive.store import ProactiveStore


def _scope(store, scope_id="scope-ops"):
    scope = Scope(
        id=scope_id,
        tenant="ops",
        name="Ops scope",
        kind="aoi",
        region="Ops region",
        center=(7.0, 50.0),
        bbox=(6.99, 49.99, 7.01, 50.01),
        asset_class="utility",
        change_types=["flood"],
    )
    store.save_scope(scope)
    store.save_plan(MonitoringPlan(scope_id=scope.id))
    return scope


def test_quota_manager():
    store = ProactiveStore(":memory:")
    _scope(store)
    manager = QuotaManager(store)
    result = manager.check("ops")
    assert result["ok"] is True
    manager.quotas["ops"] = manager.quota("ops")
    manager.quotas["ops"].max_scopes = 1
    assert manager.check("ops")["ok"] is False
    with pytest.raises(QuotaError):
        manager.enforce("ops")
    store.close()


def test_secret_vault(tmp_path):
    vault = SecretVault(tmp_path)
    vault.put("planet", {"key": "abc"})
    assert vault.get("planet")["key"] == "abc"
    rotated = vault.rotate("planet", {"key": "def"})
    assert rotated["previousKeys"] == ["key"]
    assert vault.get("planet")["key"] == "def"


def test_batch_windows_and_airgap(tmp_path):
    windows = batch_windows(
        [
            Acquisition(id="a1", scope_id="s", source="sentinel-2", scheduled_for="2026-01-01T00:00:00+00:00"),
            Acquisition(id="a2", scope_id="s", source="sentinel-2", scheduled_for="2026-01-01T01:00:00+00:00"),
        ],
        batch_size=2,
    )
    assert windows[0]["items"] == ["a1", "a2"]
    (tmp_path / "ortho.png").write_bytes(b"x")
    store = ProactiveStore(":memory:")
    _scope(store)
    result = run_airgap(store, {"scope-ops": tmp_path})
    assert result["imported"]["scope-ops"]
    store.close()


def test_replay_and_drill(tmp_path):
    store = ProactiveStore(":memory:")
    scope = _scope(store)
    store.save_acquisition(
        Acquisition(
            id="acq-1",
            scope_id=scope.id,
            source="sentinel-2",
            scheduled_for="2026-01-01T00:00:00+00:00",
            status="failed",
            idempotency_key="ops:1",
        )
    )
    replayed = replay(store, "acq-1")
    assert replayed.status == "planned"
    drill = backup_restore_drill(store, tmp_path)
    assert drill["ok"] is True
    store.close()


def test_blue_green():
    store = ProactiveStore(":memory:")
    deploy = BlueGreen(store)
    assert deploy.current()["color"] == "blue"
    promoted = deploy.promote("1.5.0")
    assert promoted["color"] == "green"
    assert promoted["version"] == "1.5.0"
    rolled = deploy.rollback()
    assert rolled["version"] == promoted["previous"]
    store.close()


def test_job_queue_and_object_store(tmp_path):
    store = ProactiveStore(":memory:")
    queue = JobQueue(store)
    job = queue.enqueue("alerts", {"alert": "A"})
    claimed = queue.claim("alerts")
    assert claimed[0]["id"] == job
    queue.fail(job, "demo")
    assert queue.stats("alerts")["counts"]["queued"] == 1
    queue.replay(job)
    queue.complete(job)
    assert queue.stats("alerts")["counts"]["done"] == 1
    objects = LocalObjectStore(tmp_path / "objects")
    objects.put("tenant-a/a.txt", b"hello")
    assert objects.get("tenant-a/a.txt") == b"hello"
    assert objects.list("tenant-a")
    assert objects.delete("tenant-a/a.txt") is True
    mirror = PostgresMirror()
    assert mirror.sync(store, "demo")["mode"] == "dry-run"
    store.close()


def test_load_test_small():
    result = load_test(scopes=25, alerts_per_scope=2)
    assert result["ok"] is True
    assert result["alerts"] == 50
    assert result["alertsPerSecond"] > 0


def test_metrics_and_log():
    metrics = Metrics()
    metrics.inc("alerts", 3)
    metrics.gauge("open", 2)
    with metrics.timer("tick"):
        pass
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["alerts"] == 3
    assert snapshot["gauges"]["open"] == 2
    assert snapshot["timings"]["tick"]["count"] == 1
    assert structured_log("test", ok=True)["event"] == "test"
    assert metrics_snapshot()["at"]
