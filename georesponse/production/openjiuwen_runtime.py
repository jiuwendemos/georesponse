"""Real openjiuwen agent backend.

This follows the coachme integration pattern: openjiuwen is imported only in this
module, tools are plain callables, and the model is configured from environment
settings.  It is optional: if openjiuwen is unavailable, the live OpenAI-compatible
backend can be used instead.
"""

from __future__ import annotations

import json
from typing import Any

from ..proactive.engine import ProactiveEngine
from .config import Settings, get_settings


class OpenJiuwenUnavailable(RuntimeError):
    pass


def _require():
    try:
        from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
        from openjiuwen.core.foundation.tool import tool
        from openjiuwen.core.runner import Runner
        from openjiuwen.harness import create_deep_agent
    except Exception as exc:  # pragma: no cover - host dependent
        raise OpenJiuwenUnavailable(f"openjiuwen is not available: {exc}") from exc
    return Model, ModelClientConfig, ModelRequestConfig, tool, Runner, create_deep_agent


SYSTEM = """You are the GeoResponse analyst agent.
You help a human decide where to send response teams and what to review.
Use only the tools. Never invent data. Every write is a proposal requiring human approval.
No automated claim approval, no automatic dispatch, no surveillance.
"""


class OpenJiuwenAgent:
    def __init__(self, engine: ProactiveEngine, settings: Settings | None = None) -> None:
        self.engine = engine
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self.settings.llm.configured

    def _tool(self, name: str, args: dict, tenant: str) -> dict:
        from .agent import LiveAgent

        return LiveAgent(self.engine, self.settings)._tool(name, args, tenant)

    def _tools(self, tenant: str) -> list[Any]:
        _Model, _Client, _Request, tool, _Runner, _create = _require()

        def get_briefing() -> str:
            """Return current portfolio, open alerts, SLA and fatigue."""
            return json.dumps(self._tool("get_briefing", {}, tenant), default=str)

        def list_alerts(status: str = "open", severity: str = "", scope_id: str = "", limit: int = 10) -> str:
            """List alerts. status can be open/new/acknowledged/assigned/investigating/resolved/dismissed; severity red/orange/yellow."""
            return json.dumps(self._tool("list_alerts", {"status": status, "severity": severity, "scope_id": scope_id, "limit": limit}, tenant), default=str)

        def get_alert(alert_id: str) -> str:
            """Get one alert with explanation and SLA."""
            return json.dumps(self._tool("get_alert", {"alert_id": alert_id}, tenant), default=str)

        def get_coverage() -> str:
            """Return coverage, freshness and blind spots by scope."""
            return json.dumps(self._tool("get_coverage", {}, tenant), default=str)

        def propose_assignment(alert_id: str, team: str) -> str:
            """Propose assigning a team to an alert. Does not mutate."""
            return json.dumps(self._tool("propose_assignment", {"alert_id": alert_id, "team": team}, tenant), default=str)

        def propose_dismissal(alert_id: str, reason: str, note: str = "") -> str:
            """Propose dismissing an alert with a reason. Does not mutate."""
            return json.dumps(self._tool("propose_dismissal", {"alert_id": alert_id, "reason": reason, "note": note}, tenant), default=str)

        def propose_handoff(alert_id: str, target: str) -> str:
            """Propose a draft assessment, claim, inspection or dispatch. Does not send."""
            return json.dumps(self._tool("propose_handoff", {"alert_id": alert_id, "target": target}, tenant), default=str)

        return [tool(get_briefing), tool(list_alerts), tool(get_alert), tool(get_coverage), tool(propose_assignment), tool(propose_dismissal), tool(propose_handoff)]

    async def chat(self, message: str, *, tenant: str, history: list[dict] | None = None, context: dict | None = None) -> dict:
        if not self.configured:
            raise OpenJiuwenUnavailable("LLM agent is not configured")
        Model, ModelClientConfig, ModelRequestConfig, _tool, Runner, create_deep_agent = _require()
        settings = self.settings.llm
        client = ModelClientConfig(
            client_provider=settings.provider,
            api_key=settings.api_key,
            api_base=settings.base_url,
            timeout=settings.timeout,
            verify_ssl=False,
        )
        request = ModelRequestConfig(model=settings.model, temperature=settings.temperature, top_p=0.9)
        model = Model(model_client_config=client, model_config=request)
        agent = create_deep_agent(
            model=model,
            system_prompt=SYSTEM,
            tools=self._tools(tenant),
            max_iterations=6,
            parallel_tool_calls=False,
        )
        try:
            await Runner.start()
        except Exception:
            pass
        prompt = message
        if context:
            safe = {key: value for key, value in context.items() if key in {"mode", "scenarioId", "alertId", "scopeId", "filter"}}
            if safe:
                prompt = f"Current UI context: {json.dumps(safe, ensure_ascii=False)}\n\n{prompt}"
        if history:
            recent = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history[-6:] if item.get("content"))
            prompt = f"Conversation so far:\n{recent}\n\nUser: {message}"
        result = await Runner.run_agent(agent, {"query": prompt})
        if isinstance(result, dict):
            answer = result.get("output") or result.get("content") or result.get("answer") or str(result)
        else:
            answer = getattr(result, "content", None) or str(result)
        return {"answer": str(answer), "trace": [], "proposals": [], "model": settings.model, "configured": True, "backend": "openjiuwen"}
