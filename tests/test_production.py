import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from georesponse.production.auth import AuthError, authenticate, configured
from georesponse.production.config import (
    ChannelSettings,
    IntegrationSettings,
    PlatformSettings,
    Settings,
    doctor,
)
from georesponse.production.inference import OnnxDamageModel, infer_tile_pair, service_health
from georesponse.production.integrations import create_jira, create_service_now, dispatch
from georesponse.production.agent import AgentUnavailable, LiveAgent
from georesponse.proactive.models import Alert, Notification
from georesponse.production.transports import send_slack, send_teams, send_webhook


def _alert() -> Alert:
    return Alert(
        id="ALT-TEST",
        tenant="tenant-a",
        scope_id="scope-test",
        title="Test flood",
        summary="A test alert.",
        severity="red",
        urgency=0.8,
        confidence=0.9,
        change_type="flood",
        observed=0.2,
        baseline=0.03,
        lon=7.1,
        lat=50.5,
        value_eur=4_000_000,
        population=500,
    )


def _notification() -> Notification:
    return Notification(
        id="NOT-1",
        tenant="tenant-a",
        alert_id="ALT-TEST",
        channel="slack",
        recipient="ops",
        subject="Test",
        body="Body",
        payload={"text": "Test"},
    )


def test_doctor_reports_unconfigured_without_secrets():
    settings = Settings()
    result = doctor(settings)
    assert result["ready"] is False
    assert "settings" in result
    serialized = json.dumps(result)
    assert "api_key" not in serialized.lower() or "apiKey" not in serialized


def test_onnx_model_and_pair():
    model = OnnxDamageModel()
    score = model.predict([{"extent": 0.9, "confidence": 0.9, "cloud": 0.02, "sar": 0.8, "value": 0.5, "population": 0.2, "access": 0.9}])
    assert 0 <= score[0] <= 1
    health = service_health()
    assert health["ok"] is True
    root = Path("web/public/data/real/ahr-2021-flood")
    result = infer_tile_pair(root / "ahr-2021-flood-before.png", root / "ahr-2021-flood-after.png")
    assert 0 <= result["probability"] <= 1
    assert result["device"] in {"cpu", "npu", "accelerator"}


def test_slack_teams_webhook_transports_with_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = ChannelSettings(slack_webhook="https://slack.test/hook", teams_webhook="https://teams.test/hook", generic_webhook="https://hook.test")
    notification = _notification()
    assert send_slack(notification, settings=settings, client=client)["status"] == 200
    assert send_teams(notification, settings=settings, client=client)["status"] == 200
    assert send_webhook(notification, settings=settings, client=client)["status"] == 200


def test_live_jira_and_servicenow_with_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"key": "GEO-1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = IntegrationSettings(
        jira_url="https://jira.test",
        jira_email="a@b.c",
        jira_token="token",
        servicenow_url="https://snow.test",
        servicenow_user="u",
        servicenow_password="p",
    )
    assert create_jira(_alert(), settings=settings, client=client)["ok"] is True
    assert create_service_now(_alert(), settings=settings, client=client)["ok"] is True
    with pytest.raises(Exception):
        dispatch("guidewire", _alert(), settings=settings, client=client)


def test_auth_api_key():
    settings = PlatformSettings(auth_mode="api-key", api_key="secret", tenant="tenant-a")
    principal = authenticate({"x-api-key": "secret"}, settings)
    assert principal.tenant == "tenant-a"
    assert configured(settings) is True
    with pytest.raises(AuthError):
        authenticate({"x-api-key": "wrong"}, settings)


def test_live_agent_tool_loop_with_mock_llm():
    import asyncio
    from georesponse.production.config import LLMSettings
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "get_briefing", "arguments": "{}"}}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "There are open alerts; review the top one."}}]})

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="test", model="test-model", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(agent.chat("brief me", tenant="demo"))
    assert result["answer"].startswith("There are open alerts")
    assert result["trace"][0]["tool"] == "get_briefing"
    assert result["configured"] is True
    store.close()


def test_live_agent_unconfigured():
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine

    store = ProactiveStore(":memory:")
    seed_demo(store)
    agent = LiveAgent(ProactiveEngine(store), Settings())
    assert agent.configured is False
    with pytest.raises(AgentUnavailable):
        import asyncio

        asyncio.run(agent.chat("hello", tenant="demo"))
    store.close()


def test_agent_refuses_unsafe_requests_without_a_call():
    import asyncio
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production.config import LLMSettings

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="test", model="test-model", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings)
    result = asyncio.run(agent.chat("Auto-approve the claim and dispatch the crew", tenant="demo"))
    assert result["refused"] is True
    assert "cannot" in result["answer"].lower()
    assert result["trace"] == []
    store.close()


def test_tool_argument_validation():
    from georesponse.production.agent import validate_tool_args

    assert validate_tool_args("get_alert", {"alert_id": "ALT-1"}) == {"alert_id": "ALT-1"}
    for name, args in [
        ("get_alert", {}),
        ("get_alert", {"alert_id": "x", "extra": 1}),
        ("get_alert", {"alert_id": 5}),
        ("propose_dismissal", {"alert_id": "x", "reason": "made-up"}),
        ("list_alerts", {"limit": 99}),
        ("not_a_tool", {}),
    ]:
        try:
            validate_tool_args(name, args)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid call {name} {args}")


def test_agent_retries_transient_errors(monkeypatch):
    import asyncio
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production import agent as agent_module
    from georesponse.production.config import LLMSettings

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(agent_module.asyncio, "sleep", no_sleep)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="test", model="test-model", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(agent.chat("brief me", tenant="demo"))
    assert result["answer"] == "ok"
    assert calls["n"] == 3
    store.close()


def test_agent_circuit_opens(monkeypatch):
    import asyncio
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production import agent as agent_module
    from georesponse.production.config import LLMSettings

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(agent_module.asyncio, "sleep", no_sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="test", model="test-model", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings, transport=httpx.MockTransport(handler))
    for _ in range(5):
        try:
            asyncio.run(agent.chat("brief me", tenant="demo"))
        except AgentUnavailable:
            continue
    try:
        asyncio.run(agent.chat("brief me", tenant="demo"))
    except AgentUnavailable as exc:
        assert "circuit" in str(exc)
    else:
        raise AssertionError("circuit did not open")
    store.close()


def test_agent_evaluation_offline():
    from georesponse.production.evaluation import evaluate_offline

    result = evaluate_offline()
    assert result["passed"] is True, result["failed"]
    assert result["cases"] >= 6


def test_agent_receives_ui_context():
    import asyncio
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production.config import LLMSettings

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="test", model="test-model", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings, transport=httpx.MockTransport(handler))
    asyncio.run(agent.chat("what changed?", tenant="demo", context={"mode": "watch", "scenarioId": "ahr-2021-flood", "alertId": "ALT-1001"}))
    system = seen["messages"][0]["content"]
    assert "ahr-2021-flood" in system
    assert "ALT-1001" in system
    assert "watch" in system
    store.close()


def test_backend_selection_openai():
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production.agent_backend import select
    from georesponse.production.config import LLMSettings

    store = ProactiveStore(":memory:")
    seed_demo(store)
    backend, resolved = select(ProactiveEngine(store), Settings(llm=LLMSettings(backend="openai", api_key="x", model="m")))
    assert resolved == "openai"
    assert backend.__class__.__name__ == "LiveAgent"
    store.close()


def test_direct_stream_yields_start_and_done():
    import asyncio
    from georesponse.proactive.store import ProactiveStore
    from georesponse.proactive.demo import seed_demo
    from georesponse.proactive.engine import ProactiveEngine
    from georesponse.production.config import LLMSettings

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hello"}}]})

    store = ProactiveStore(":memory:")
    seed_demo(store)
    settings = Settings(llm=LLMSettings(api_key="x", model="m", base_url="https://llm.test/v1"))
    agent = LiveAgent(ProactiveEngine(store), settings, transport=httpx.MockTransport(handler))

    async def collect():
        return [event async for event in agent.stream("hi", tenant="demo")]

    events = asyncio.run(collect())
    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "done"
    assert events[-1]["answer"] == "hello"
    store.close()
