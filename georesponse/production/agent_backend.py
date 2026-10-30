"""Backend selection: openjiuwen when the runtime supports it, direct otherwise."""

from __future__ import annotations

from ..proactive.engine import ProactiveEngine
from .config import Settings, get_settings


def openjiuwen_status() -> tuple[bool, str]:
    try:
        from .openjiuwen_runtime import _require

        _require()
        return True, "available"
    except Exception as exc:  # noqa: BLE001 - host dependent
        return False, str(exc)


def select(engine: ProactiveEngine, settings: Settings | None = None):
    """Return ``(backend, resolved_name)``.

    ``auto`` prefers openjiuwen when it imports and falls back to the direct
    OpenAI-compatible backend. ``openjiuwen`` fails loudly instead of falling
    back, so an operator never thinks the framework is active when it is not.
    """
    settings = settings or get_settings()
    configured = settings.llm.backend
    if configured == "openai":
        from .agent import LiveAgent

        return LiveAgent(engine, settings), "openai"
    if configured in {"openjiuwen", "auto"}:
        available, detail = openjiuwen_status()
        if available:
            from .openjiuwen_runtime import OpenJiuwenAgent

            return OpenJiuwenAgent(engine, settings), "openjiuwen"
        if configured == "openjiuwen":
            from .openjiuwen_runtime import OpenJiuwenUnavailable

            raise OpenJiuwenUnavailable(f"openjiuwen is not available: {detail}")
    from .agent import LiveAgent

    return LiveAgent(engine, settings), "openai"


def status(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    available, detail = openjiuwen_status()
    resolved = "openjiuwen" if settings.llm.backend in {"openjiuwen", "auto"} and available else "openai"
    return {
        "configured": settings.llm.backend,
        "resolved": resolved,
        "openjiuwenAvailable": available,
        "openjiuwenDetail": detail if not available else "available",
    }
