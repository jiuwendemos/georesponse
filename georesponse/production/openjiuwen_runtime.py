"""Real openjiuwen backend with sessions, planning, subagents and streaming.

openjiuwen is imported only in this module. The seven GeoResponse tools are the
same tools the direct OpenAI-compatible backend uses; openjiuwen adds the
orchestration layer: an AgentCard, task planning, specialised subagents, a
policy rail, a session per tenant/alert and an event stream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from ..proactive.engine import ProactiveEngine
from .config import Settings, get_settings

PROMPT_VERSION = "geo-openjiuwen-2026.1"
ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "runtime" / "agent-workspace"
SESSION_TURNS = 8

SYSTEM = """You are the GeoResponse analyst agent, running on the openjiuwen DeepAgent harness.
You help a human decide where to send response teams and what to review.
Rules:
- Use only the tools provided. Never invent an alert, site, number or source.
- Every write is a proposal. Never claim an action was applied.
- No automated claim approval, no automatic crew dispatch, no surveillance.
- For multi-step questions, plan first, then use the specialised subagents.
- Be concise, operational and explicit about confidence and uncertainty.
"""

EVIDENCE_PROMPT = """You are the evidence analyst. Explain one alert: what changed, the baseline,
the confidence and the imagery provenance. Use get_alert and get_briefing only. Never propose a write."""
COVERAGE_PROMPT = """You are the coverage analyst. Report freshness, blind spots, readiness and SLA.
Use get_coverage and list_alerts only. Never propose a write."""
CLAIMS_PROMPT = """You are the claims and field drafter. Prepare a draft assessment, claim, inspection or
dispatch for a named alert. Use propose_handoff and propose_assignment only; they create proposals and
never mutate. State clearly that a human must approve."""
VERIFIER_PROMPT = """You are the verifier. Check that a proposed claim is grounded in a real alert and
tool result. Use get_alert and get_briefing only. If evidence is missing, say so. Never propose a write."""


class OpenJiuwenUnavailable(RuntimeError):
    pass


def _require():
    try:
        from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
        from openjiuwen.core.foundation.tool import tool
        from openjiuwen.core.runner import Runner
        from openjiuwen.core.single_agent.rail.base import AgentRail
        from openjiuwen.core.single_agent.schema.agent_card import AgentCard
        from openjiuwen.core.session.stream.base import BaseStreamMode
        from openjiuwen.harness import create_deep_agent
        from openjiuwen.harness.schema.config import SubAgentConfig
    except Exception as exc:  # pragma: no cover - host dependent
        raise OpenJiuwenUnavailable(f"openjiuwen is not available: {exc}") from exc
    return {
        "Model": Model,
        "ModelClientConfig": ModelClientConfig,
        "ModelRequestConfig": ModelRequestConfig,
        "tool": tool,
        "Runner": Runner,
        "AgentRail": AgentRail,
        "AgentCard": AgentCard,
        "BaseStreamMode": BaseStreamMode,
        "create_deep_agent": create_deep_agent,
        "SubAgentConfig": SubAgentConfig,
    }


def _card(AgentCard, *, id: str, name: str, description: str):
    return AgentCard(id=id, name=name, description=description)


class _RecordingRail:
    """Factory for a rail that enforces the tool allowlist and records traces."""

    @staticmethod
    def build(AgentRail, trace: list[dict], allowed: set[str]):
        class GeoResponsePolicyRail(AgentRail):
            priority = 90

            async def before_tool_call(self, ctx) -> None:  # noqa: ANN001
                name = getattr(ctx.inputs, "tool_name", "")
                if name and name not in allowed:
                    raise PermissionError(f"tool {name} is not allowed by the GeoResponse policy")
                trace.append({"tool": name, "arguments": getattr(ctx.inputs, "tool_call", {})})

            async def after_tool_call(self, ctx) -> None:  # noqa: ANN001
                name = getattr(ctx.inputs, "tool_name", "")
                result = getattr(ctx.inputs, "tool_result", None)
                if name:
                    trace.append({"tool": name, "result": result})

        return GeoResponsePolicyRail()


class OpenJiuwenAgent:
    def __init__(self, engine: ProactiveEngine, settings: Settings | None = None) -> None:
        self.engine = engine
        self.settings = settings or get_settings()
        self._runner_started = False

    @property
    def configured(self) -> bool:
        return self.settings.llm.configured

    # ------------------------------------------------------------------ tools
    def _tool(self, name: str, args: dict, tenant: str) -> dict:
        from .agent import LiveAgent

        return LiveAgent(self.engine, self.settings)._tool(name, args, tenant)

    def _tool_map(self, tenant: str) -> dict[str, Any]:
        info = _require()
        tool = info["tool"]

        def get_briefing() -> str:
            """Return current portfolio, open alerts, SLA and fatigue."""
            return json.dumps(self._tool("get_briefing", {}, tenant), default=str)

        def list_alerts(status: str = "open", severity: str = "", scope_id: str = "", limit: int = 10) -> str:
            """List alerts. status is open/new/acknowledged/assigned/investigating/resolved/dismissed."""
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

        return {
            "get_briefing": tool(get_briefing),
            "list_alerts": tool(list_alerts),
            "get_alert": tool(get_alert),
            "get_coverage": tool(get_coverage),
            "propose_assignment": tool(propose_assignment),
            "propose_dismissal": tool(propose_dismissal),
            "propose_handoff": tool(propose_handoff),
        }

    def _subagents(self, tools: dict[str, Any], rail):
        info = _require()
        AgentCard = info["AgentCard"]
        SubAgentConfig = info["SubAgentConfig"]
        return [
            SubAgentConfig(
                agent_card=_card(AgentCard, id="gr-evidence", name="Evidence analyst", description="Explains one alert with evidence and provenance."),
                system_prompt=EVIDENCE_PROMPT,
                tools=[tools["get_alert"], tools["get_briefing"], tools["get_coverage"]],
                display_name="Evidence",
                role="analyst",
                rails=[rail],
                max_iterations=3,
            ),
            SubAgentConfig(
                agent_card=_card(AgentCard, id="gr-coverage", name="Coverage analyst", description="Reports freshness, blind spots and SLA."),
                system_prompt=COVERAGE_PROMPT,
                tools=[tools["get_coverage"], tools["list_alerts"]],
                display_name="Coverage",
                role="watch",
                rails=[rail],
                max_iterations=3,
            ),
            SubAgentConfig(
                agent_card=_card(AgentCard, id="gr-claims", name="Claims drafter", description="Prepares proposal-only claim, inspection or dispatch drafts."),
                system_prompt=CLAIMS_PROMPT,
                tools=[tools["propose_handoff"], tools["propose_assignment"], tools["get_alert"]],
                display_name="Claims",
                role="claims",
                rails=[rail],
                max_iterations=4,
            ),
            SubAgentConfig(
                agent_card=_card(AgentCard, id="gr-verifier", name="Verifier", description="Checks that claims are grounded in tool results."),
                system_prompt=VERIFIER_PROMPT,
                tools=[tools["get_alert"], tools["get_briefing"]],
                display_name="Verifier",
                role="verifier",
                rails=[rail],
                max_iterations=2,
            ),
        ]

    # --------------------------------------------------------------- sessions
    def _session_id(self, tenant: str, context: dict | None) -> str:
        context = context or {}
        anchor = context.get("alertId") or context.get("scopeId") or context.get("scenarioId") or "general"
        return f"{tenant}:{anchor}"

    def _load_session(self, session_id: str) -> list[dict]:
        raw = self.engine.store.meta_get(f"agent-session:{session_id}")
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    def _save_session(self, session_id: str, history: list[dict], user: str, answer: str) -> None:
        turns = [*history, {"role": "user", "content": user}, {"role": "assistant", "content": answer}]
        self.engine.store.meta_set(f"agent-session:{session_id}", json.dumps(turns[-SESSION_TURNS:], ensure_ascii=False))

    # ------------------------------------------------------------------ build
    def _build(self, tenant: str, context: dict | None):
        info = _require()
        settings = self.settings.llm
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        client = info["ModelClientConfig"](
            client_provider=settings.provider,
            api_key=settings.api_key,
            api_base=settings.base_url,
            timeout=settings.timeout,
            verify_ssl=False,
        )
        request = info["ModelRequestConfig"](model=settings.model, temperature=settings.temperature, top_p=0.9)
        model = info["Model"](model_client_config=client, model_config=request)
        tools = self._tool_map(tenant)
        trace: list[dict] = []
        rail = _RecordingRail.build(info["AgentRail"], trace, set(tools))
        agent = info["create_deep_agent"](
            model=model,
            card=_card(info["AgentCard"], id="geo-response-agent", name="GeoResponse analyst", description="Geospatial decision analyst with proposal-only writes."),
            system_prompt=SYSTEM,
            tools=list(tools.values()),
            subagents=self._subagents(tools, rail),
            rails=[rail],
            enable_task_planning=True,
            enable_task_loop=False,
            add_general_purpose_agent=False,
            max_iterations=6,
            workspace=str(WORKSPACE),
            parallel_tool_calls=False,
            enable_security_rail=False,
            language="en",
        )
        return agent, trace, tools

    async def _start(self) -> None:
        if self._runner_started:
            return
        Runner = _require()["Runner"]
        try:
            await Runner.start()
        except Exception:
            pass
        self._runner_started = True

    def _prompt(self, message: str, history: list[dict], context: dict | None) -> str:
        parts = []
        if context:
            safe = {key: value for key, value in context.items() if key in {"mode", "scenarioId", "alertId", "scopeId", "filter"}}
            if safe:
                parts.append("Current UI context: " + json.dumps(safe, ensure_ascii=False))
        if history:
            recent = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history[-SESSION_TURNS:] if item.get("content"))
            if recent:
                parts.append("Conversation so far:\n" + recent)
        parts.append(f"User: {message}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------- chat
    async def chat(self, message: str, *, tenant: str, history: list[dict] | None = None, context: dict | None = None) -> dict:
        if not self.configured:
            raise OpenJiuwenUnavailable("LLM agent is not configured")
        info = _require()
        Runner = info["Runner"]
        session_id = self._session_id(tenant, context)
        stored = self._load_session(session_id)
        merged = [*(history or []), *stored] if not stored else stored
        agent, trace, _tools = self._build(tenant, context)
        await self._start()
        prompt = self._prompt(message, merged, context)

        before = self._pending_ids(tenant)
        result = await Runner.run_agent(agent, {"query": prompt}, session=session_id)
        answer = self._answer_text(result)
        after = self._pending_ids(tenant)
        proposals = self._proposals(tenant, after - before, context)
        self._save_session(session_id, merged, message, answer)
        return {
            "answer": answer,
            "trace": self._clean_trace(trace),
            "proposals": proposals,
            "model": self.settings.llm.model,
            "configured": True,
            "backend": "openjiuwen",
            "sessionId": session_id,
            "promptVersion": PROMPT_VERSION,
            "subagents": ["evidence", "coverage", "claims", "verifier"],
        }

    # -------------------------------------------------------------- streaming
    async def stream(self, message: str, *, tenant: str, history: list[dict] | None = None, context: dict | None = None) -> AsyncIterator[dict]:
        if not self.configured:
            raise OpenJiuwenUnavailable("LLM agent is not configured")
        info = _require()
        Runner = info["Runner"]
        BaseStreamMode = info["BaseStreamMode"]
        session_id = self._session_id(tenant, context)
        stored = self._load_session(session_id)
        merged = [*(history or []), *stored] if not stored else stored
        agent, trace, _tools = self._build(tenant, context)
        await self._start()
        prompt = self._prompt(message, merged, context)
        before = self._pending_ids(tenant)
        yield {"type": "start", "sessionId": session_id, "promptVersion": PROMPT_VERSION}
        final_text = ""
        async for event in Runner.run_agent_streaming(
            agent,
            {"query": prompt},
            session=session_id,
            stream_modes=[BaseStreamMode.OUTPUT, BaseStreamMode.TRACE],
        ):
            payload = event.model_dump() if hasattr(event, "model_dump") else event
            text = self._event_text(payload)
            if text:
                final_text = text if len(text) > len(final_text) else final_text
            yield {"type": "event", "payload": payload}
        after = self._pending_ids(tenant)
        proposals = self._proposals(tenant, after - before, context)
        if not final_text:
            final_text = "The agent finished without a text answer. Review the trace."
        self._save_session(session_id, merged, message, final_text)
        yield {
            "type": "done",
            "answer": final_text,
            "trace": self._clean_trace(trace),
            "proposals": proposals,
            "sessionId": session_id,
            "promptVersion": PROMPT_VERSION,
            "model": self.settings.llm.model,
        }

    # ---------------------------------------------------------------- helpers
    def _pending_ids(self, tenant: str) -> set[str]:
        from ..proactive.proposals import ProposalStore

        return {proposal.id for proposal in ProposalStore(self.engine.store).pending(tenant)}

    def _proposals(self, tenant: str, ids: set[str], context: dict | None) -> list[dict]:
        from ..proactive.proposals import ProposalStore

        store = ProposalStore(self.engine.store)
        items = []
        for proposal_id in ids:
            try:
                proposal = store.get(proposal_id)
            except Exception:
                continue
            if context and context.get("alertId") and proposal.alert_id != context.get("alertId"):
                continue
            items.append({**proposal.payload, "id": proposal.id, "action": proposal.action, "alertId": proposal.alert_id})
        return items

    def _answer_text(self, result: Any) -> str:
        if isinstance(result, dict):
            for key in ("output", "content", "answer", "result"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
            return str(result)
        return str(getattr(result, "content", None) or result)

    def _event_text(self, payload: Any) -> str:
        if isinstance(payload, dict):
            body = payload.get("payload")
            if isinstance(body, str):
                return body
            if isinstance(body, dict):
                for key in ("content", "output", "answer", "text"):
                    value = body.get(key)
                    if isinstance(value, str):
                        return value
        return ""

    def _clean_trace(self, trace: list[dict]) -> list[dict]:
        """Keep calls and short results; drop duplicate after-call records."""
        cleaned = []
        for item in trace:
            if "result" in item:
                continue
            arguments = item.get("arguments")
            if hasattr(arguments, "model_dump"):
                arguments = arguments.model_dump()
            cleaned.append({"tool": item.get("tool"), "arguments": arguments})
        return cleaned
