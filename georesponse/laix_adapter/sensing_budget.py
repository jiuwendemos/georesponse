"""Map a monitoring plan to LAIX's resource policy.

The point is not to acquire more imagery.  It is to decide which acquisition or
model call is worth making under the plan's budget, and to record what was
skipped and why.
"""

from __future__ import annotations

from laix import Budget, ResourcePlan, ResourcePolicy, SensingOption

from ..proactive.models import MonitoringPlan

# Relative acquisition cost in EUR per tasking request.  Sentinel is free at
# the point of use; commercial tasking is illustrative and must be replaced by
# the contract's real price before an operational budget decision.
SOURCE_COST = {
    "sentinel-1": 0.0,
    "sentinel-2": 0.0,
    "landsat": 0.0,
    "planet": 450.0,
    "maxar": 900.0,
    "airbus": 800.0,
    "iceye": 1_200.0,
    "capella": 1_100.0,
}

SOURCE_GAIN = {
    "sentinel-1": 0.80,
    "sentinel-2": 0.65,
    "landsat": 0.50,
    "planet": 0.78,
    "maxar": 0.82,
    "airbus": 0.80,
    "iceye": 0.88,
    "capella": 0.86,
}


def options_for_plan(plan: MonitoringPlan) -> list[SensingOption]:
    options: list[SensingOption] = [
        SensingOption(name="coverage-check", tier="cheap", cost=0.0, latency_ms=50, information_gain=0.2)
    ]
    for source in plan.sources:
        key = source.strip().lower()
        commercial = SOURCE_COST.get(key, 0.0) > 0
        options.append(
            SensingOption(
                name=f"acquire:{key}",
                tier="deep" if commercial else "cheap",
                cost=SOURCE_COST.get(key, 0.0),
                latency_ms=3_600_000 if commercial else 900_000,
                information_gain=SOURCE_GAIN.get(key, 0.6),
            )
        )
    options.append(
        SensingOption(
            name="infer:change-model",
            tier="deep",
            cost=12.0,
            latency_ms=4_000,
            information_gain=0.7,
        )
    )
    return options


def budget_for_plan(plan: MonitoringPlan) -> Budget:
    return Budget(
        max_deep_calls=max(1, len(plan.sources)),
        max_cost=max(1.0, float(plan.budget_eur_per_month)),
        max_latency_ms=7_200_000,
    )


def schedule_for_plan(plan: MonitoringPlan, *, uncertainty: float) -> ResourcePlan:
    policy = ResourcePolicy()
    return policy.schedule(options_for_plan(plan), budget=budget_for_plan(plan), uncertainty=uncertainty)


def estimate(plan: MonitoringPlan, *, uncertainty: float) -> dict:
    plan_result = schedule_for_plan(plan, uncertainty=uncertainty)
    return {
        "allowed": list(plan_result.allowed),
        "skipped": [dict(item) for item in plan_result.skipped],
        "deepCalls": plan_result.deep_calls,
        "estimatedCostEur": round(plan_result.cost, 2),
        "budgetEur": round(budget_for_plan(plan).max_cost, 2),
        "uncertainty": round(float(uncertainty), 3),
    }
