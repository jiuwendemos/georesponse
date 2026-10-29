import json

from georesponse.audit import append_event, audit_csv, read_events, verify_chain


def test_audit_chain_is_hash_linked(tmp_path):
    path = tmp_path / "audit.jsonl"
    append_event(path, {"action": "review.approved", "siteId": "S02", "analyst": "A. Weber"})
    append_event(path, {"action": "review.rejected", "siteId": "S01", "analyst": "A. Weber"})
    events = read_events(path)
    assert len(events) == 2
    assert events[0]["prev"] == "0" * 64
    assert events[1]["prev"] == events[0]["hash"]
    ok, message = verify_chain(events)
    assert ok, message
    assert "siteId" in audit_csv(events)


def test_tampering_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    append_event(path, {"action": "one"})
    append_event(path, {"action": "two"})
    events = read_events(path)
    events[0]["action"] = "tampered"
    ok, message = verify_chain(events)
    assert not ok
    assert "hash" in message or "link" in message


def test_missing_file_is_empty_not_crash(tmp_path):
    assert read_events(tmp_path / "missing.jsonl") == []
    payload = json.dumps({"ok": True})
    assert payload
