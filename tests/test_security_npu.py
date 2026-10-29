import pytest

from georesponse.npu import NPUBroker, InferenceJob, plan_batches
from georesponse.security import TenantError, TenantStore, privacy_review, redact_pii


def test_tenant_isolation(tmp_path):
    store = TenantStore(tmp_path)
    store.write("insurer-a", "assessments/one.json", {"ok": True})
    store.write("insurer-b", "assessments/one.json", {"ok": False})
    assert store.read("insurer-a", "assessments/one.json")["ok"] is True
    assert store.read("insurer-b", "assessments/one.json")["ok"] is False
    assert store.list_tenants() == ["insurer-a", "insurer-b"]


def test_path_escape_is_blocked(tmp_path):
    store = TenantStore(tmp_path)
    store.ensure("insurer-a")
    with pytest.raises(TenantError):
        store.write("insurer-a", "../escape.json", {"x": 1})
    with pytest.raises(TenantError):
        store.read("Bad Tenant!", "one.json")


def test_privacy_review_and_redaction():
    review = privacy_review({"lawful_basis", "human_review"})
    assert review["done"] == 2
    assert review["open"] > 0
    redacted = redact_pii({"holder": "Ada Lovelace", "address": "1 Main St", "claimRef": "CLM-123"})
    assert redacted["holder"] == "Ad***"
    assert redacted["claimRef"].endswith("***")


def test_npu_broker_queue_and_benchmark():
    broker = NPUBroker(batch_size=4)
    broker.register_model("change", "/models/change.bin")
    job = broker.submit(InferenceJob(id="job-1", tiles=16, model="change"))
    processed = broker.run(lambda j: {"tiles": j.tiles, "changed": 3})
    assert processed[0].status == "done"
    assert job.result["elapsedMs"] >= 0
    status = broker.status()
    assert status["done"] == 1
    assert broker.benchmark(64)["throughputTilesPerMinute"] > 0


def test_plan_batches():
    batches = plan_batches([{"id": i} for i in range(10)], 4)
    assert [len(b) for b in batches] == [4, 4, 2]
