"""LAIX: a domain-neutral decision layer.

The package answers one question for a live application: *given what is
happening, what the app is trying to achieve, what it can afford and what needs
approval, should it wait, ask, guide, act, verify or escalate?*

It is intentionally standard-library only.  The host application provides
domain adapters; the decision layer never imports them.
"""

from .contracts import (
    CONTRACT_NAMES,
    CONTRACTS,
    CONSTRAINT_KINDS,
    HORIZONS,
    OUTCOME_DIRECTIONS,
    OUTCOME_LABELS,
    PHASES,
    RECEIPT_STATUSES,
    SCHEMA_VERSION,
    VERBS,
    Action,
    Belief,
    Constraint,
    Decision,
    Goal,
    Observation,
    Outcome,
    Receipt,
    Situation,
    Trace,
    confidence_band,
    iso,
    parse_iso,
    utcnow,
)
from .execution import ApprovalRequired, ExecutionBridge, UnknownAction
from .outcome import OutcomeLedger
from .policy import DecisionPolicy, PolicyConfig, PolicyRequest, decide
from .resources import Budget, ResourcePlan, ResourcePolicy, SensingOption
from .runtime import DecisionRuntime
from .state import ExperienceState

POLICY_VERSION = "2026.1"

__all__ = [
    "Action",
    "ApprovalRequired",
    "Belief",
    "Budget",
    "CONTRACT_NAMES",
    "CONTRACTS",
    "CONSTRAINT_KINDS",
    "Constraint",
    "Decision",
    "DecisionPolicy",
    "DecisionRuntime",
    "ExecutionBridge",
    "ExperienceState",
    "Goal",
    "HORIZONS",
    "Observation",
    "Outcome",
    "OutcomeLedger",
    "OUTCOME_DIRECTIONS",
    "OUTCOME_LABELS",
    "PHASES",
    "POLICY_VERSION",
    "PolicyConfig",
    "PolicyRequest",
    "RECEIPT_STATUSES",
    "Receipt",
    "ResourcePlan",
    "ResourcePolicy",
    "SCHEMA_VERSION",
    "SensingOption",
    "Situation",
    "Trace",
    "UnknownAction",
    "VERBS",
    "confidence_band",
    "decide",
    "iso",
    "parse_iso",
    "utcnow",
]
