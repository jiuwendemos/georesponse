"""Live tool-using agent over an OpenAI-compatible endpoint.

The model never mutates state.  Read tools return grounded GeoResponse data;
write tools return proposals that require a human approval in the UI/API.
Set ``GEORESPONSE_LLM_API_KEY`` and ``GEORESPONSE_LLM_MODEL`` to enable it.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from ..proactive.engine import ProactiveEngine
from .config import Settings, get_settings

SYSTEM = """You are the GeoResponse analyst agent.
You help a human decide where to send response teams and what to review.
Rules:
- Use only the tools provided. Never invent an alert, site, number or source.
- Every write is a proposal. Never claim an action was applied.
- No automated claim approval, no automatic crew dispatch, no surveillance.
- Be concise, operational and explicit about confidence and uncertainty.
- Prefer the Watch alert lifecycle; when the question is about the stage scenario,
  say that the scenario is a demo pack and the live Watch data is separate.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_briefing",
            "description": "Current portfolio briefing: scopes, open alerts, SLA, fatigue, pilot gate.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alerts",
            "description": "List alerts with optional status/severity/scope filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "new", "acknowledged", "assigned", "investigating", "resolved", "dismissed"]},
                    "severity": {"type": "string", "enum": ["red", "orange", "yellow"]},
                    "scope_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alert",
            "description": "Full alert, explanation and SLA state.",
            "parameters": {"type": "object", "properties": {"alert_id": {"type": "string"}}, "required": ["alert_id"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_coverage",
            "description": "Coverage, freshness and blind spots by scope.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_assignment",
            "description": "Propose assigning a team to an alert's site. Does not mutate.",
            "parameters": {
                "type": "object",
                "properties": {"alert_id": {"type": "string"}, "team": {"type": "string"}},
                "required": ["alert_id", "team"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_dismissal",
            "description": "Propose dismissing an alert with a reason. Does not mutate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string"},
                    "reason": {"type": "string", "enum": ["false_positive", "known_event", "cloud_shadow", "no_action", "duplicate", "access", "other"]},
                    "note": {"type": "string"},
                },
                "required": ["alert_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_handoff",
            "description": "Propose a claim, inspection, dispatch or assessment draft. Does not send.",
            "parameters": {
                "type": "object",
                "properties": {"alert_id": {"type": "string"}, "target": {"type": "string", "enum": ["assessment", "claim", "inspection", "dispatch"]}},
                "required": ["alert_id", "target"],
                "additionalProperties": False,
            },
        },
    },
]


PROMPT_VERSION = "geo-agent-2026.1"

TOOL_SCHEMAS = {tool["function"]["name"]: tool["function"]["parameters"] for tool in TOOLS}

UNSAFE_PATTERNS = (
    "approve the claim automatically",
    "auto-approve",
    "automatically approve",
    "dispatch without approval",
    "dispatch automatically",
    "auto dispatch",
    "face recognition",
    "track the person",
    "identify the person",
    "surveil",
    "ignore the audit",
    "bypass approval",
)


def validate_tool_args(name: str, args: Any) -> dict:
    """Validate a tool call against the schema the model was given."""
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        raise ValueError(f"unknown tool: {name}")
    if not isinstance(args, dict):
        raise ValueError("tool arguments must be an object")
    properties = schema.get("properties", {})
    for required in schema.get("required", []):
        if required not in args:
            raise ValueError(f"{name}: missing required argument {required}")
    if schema.get("additionalProperties") is False:
        extra = set(args) - set(properties)
        if extra:
            raise ValueError(f"{name}: unexpected arguments {sorted(extra)}")
    for key, value in args.items():
        spec = properties.get(key, {})
        kind = spec.get("type")
        if kind == "string" and not isinstance(value, str):
            raise ValueError(f"{name}.{key} must be a string")
        if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(f"{name}.{key} must be an integer")
        if kind == "number" and not isinstance(value, (int, float)):
            raise ValueError(f"{name}.{key} must be a number")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"{name}.{key} must be one of {spec['enum']}")
        if "minimum" in spec and isinstance(value, (int, float)) and value < spec["minimum"]:
            raise ValueError(f"{name}.{key} is below the minimum")
        if "maximum" in spec and isinstance(value, (int, float)) and value > spec["maximum"]:
            raise ValueError(f"{name}.{key} is above the maximum")
    return args


def refusal_for(message: str) -> str | None:
    lowered = message.lower()
    if any(pattern in lowered for pattern in UNSAFE_PATTERNS):
        return (
            "I cannot do that. GeoResponse never approves claims, dispatches crews, "
            "or performs surveillance automatically. I can prepare a proposal with "
            "evidence and a named human approver, or explain the current alert."
        )
    return None


class AgentUnavailable(RuntimeError):
    pass


class LiveAgent:
    def __init__(self, engine: ProactiveEngine, settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.engine = engine
        self.settings = settings or get_settings()
        self.transport = transport
        self._failures = 0
        self._opened_at = 0.0

    @property
    def configured(self) -> bool:
        return self.settings.llm.configured

    def _tool(self, name: str, args: dict[str, Any], tenant: str) -> dict:
        store = self.engine.store
        if name == "get_briefing":
            dashboard = self.engine.dashboard(tenant)
            return {
                "scopes": dashboard["scopes"],
                "activeScopes": dashboard["activeScopes"],
                "alerts": dashboard["alerts"],
                "open": dashboard["open"],
                "highRisk": dashboard["highRisk"],
                "slaBreaches": dashboard["slaBreaches"],
                "precision": dashboard["precision"],
                "fatigue": dashboard["fatigue"],
                "freshness": dashboard["freshness"],
                "pilot": self.engine.pilot_report(tenant)["gates"],
            }
        if name == "list_alerts":
            status = args.get("status")
            if status == "open":
                alerts = [a for a in store.list_alerts(tenant) if a.status in {"new", "acknowledged", "assigned", "investigating"}]
            else:
                alerts = store.list_alerts(tenant, scope_id=args.get("scope_id"), status=status)
            if args.get("severity"):
                alerts = [a for a in alerts if a.severity == args["severity"]]
            return [
                {
                    "id": a.id,
                    "title": a.title,
                    "severity": a.severity,
                    "confidence": a.confidence,
                    "status": a.status,
                    "scope": a.scope_id,
                    "assignee": a.assignee,
                    "summary": a.summary,
                }
                for a in alerts[: int(args.get("limit", 10))]
            ]
        if name == "get_alert":
            alert = store.get_alert(args["alert_id"])
            if not alert:
                return {"error": "not found"}
            return {"alert": alert.to_dict(), "explain": self.engine.explain(alert.id), "sla": __import__("georesponse.proactive.alerts", fromlist=["sla_status"]).sla_status(alert)}
        if name == "get_coverage":
            return self.engine.watch(tenant, store.list_forecasts())["coverage"]
        if name == "propose_assignment":
            alert = store.get_alert(args["alert_id"])
            if not alert:
                return {"error": "not found"}
            return {"proposal": {"action": "assign", "alertId": alert.id, "team": args["team"], "site": alert.asset}, "requiresApproval": True}
        if name == "propose_dismissal":
            alert = store.get_alert(args["alert_id"])
            if not alert:
                return {"error": "not found"}
            return {"proposal": {"action": "dismiss", "alertId": alert.id, "reason": args["reason"], "note": args.get("note", "")}, "requiresApproval": True}
        if name == "propose_handoff":
            alert = store.get_alert(args["alert_id"])
            if not alert:
                return {"error": "not found"}
            return {"proposal": {"action": "handoff", "alertId": alert.id, "target": args["target"]}, "requiresApproval": True}
        return {"error": f"unknown tool {name}"}

    async def _post(self, client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> httpx.Response:
        """POST with retry, backoff and a small circuit breaker."""
        if self._failures >= 5 and (time.time() - self._opened_at) < 30:
            raise AgentUnavailable("agent circuit is open after repeated upstream failures")
        last: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(f"upstream {response.status_code}", request=response.request, response=response)
                response.raise_for_status()
                self._failures = 0
                return response
            except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.4 * (2 ** attempt))
        self._failures += 1
        self._opened_at = time.time()
        raise AgentUnavailable(f"agent upstream failed after retries: {last}")

    async def chat(self, message: str, *, tenant: str, history: list[dict] | None = None) -> dict:
        if not self.configured:
            raise AgentUnavailable("LLM agent is not configured. Run `georesponse doctor`.")
        refused = refusal_for(message)
        if refused:
            return {
                "answer": refused,
                "trace": [],
                "proposals": [],
                "model": self.settings.llm.model,
                "configured": True,
                "refused": True,
                "promptVersion": PROMPT_VERSION,
            }
        settings = self.settings.llm
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
        for item in history or []:
            if item.get("role") in {"user", "assistant"} and item.get("content"):
                messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": message})
        trace: list[dict] = []
        proposals: list[dict] = []
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        url = settings.base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=settings.timeout, transport=self.transport) as client:
            for _ in range(5):
                response = await self._post(client, url, headers, {
                    "model": settings.model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": settings.temperature,
                })
                payload = response.json()
                choice = payload["choices"][0]["message"]
                tool_calls = choice.get("tool_calls") or []
                if not tool_calls:
                    return {
                        "answer": choice.get("content") or "",
                        "trace": trace,
                        "proposals": proposals,
                        "model": settings.model,
                        "configured": True,
                        "promptVersion": PROMPT_VERSION,
                    }
                messages.append({"role": "assistant", "content": choice.get("content") or "", "tool_calls": tool_calls})
                for call in tool_calls:
                    name = call["function"]["name"]
                    try:
                        args = validate_tool_args(name, json.loads(call["function"].get("arguments") or "{}"))
                        result = self._tool(name, args, tenant)
                    except (ValueError, json.JSONDecodeError) as exc:
                        result = {"error": f"invalid tool call: {exc}"}
                        args = {}
                        trace.append({"tool": name, "arguments": args, "error": str(exc)})
                    if isinstance(result, dict) and result.get("requiresApproval"):
                        proposals.append(result["proposal"])
                    trace.append({"tool": name, "arguments": args, "result": result})
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, default=str)})
        return {
            "answer": "I reached the tool iteration limit. Review the trace and ask a narrower question.",
            "trace": trace,
            "proposals": proposals,
            "model": settings.model,
            "configured": True,
            "promptVersion": PROMPT_VERSION,
        }
