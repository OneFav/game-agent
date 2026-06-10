from __future__ import annotations

from typing import Any


def satisfies_hard_constraints(metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> bool:
    """Return whether all configured hard constraints pass."""
    for constraint in evaluation_metrics.get("hard_constraints", []):
        name = _required_constraint_name(constraint)
        if name not in metrics:
            raise KeyError(f"Missing hard constraint metric: {name}")
        value = float(metrics[name])
        if "max" not in constraint and "min" not in constraint:
            raise ValueError(f"Hard constraint must define max or min: {name}")
        if "max" in constraint and value > float(constraint["max"]):
            return False
        if "min" in constraint and value < float(constraint["min"]):
            return False
    return True


def ranking_key(metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> tuple[object, ...]:
    """Sort key: feasible first, primary metric next, shorter episodes last tie-break."""
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    direction = str(primary.get("direction", "maximize"))
    if primary_name not in metrics:
        raise KeyError(f"Missing primary metric: {primary_name}")
    primary_value = float(metrics[primary_name])
    primary_key = -primary_value if direction == "maximize" else primary_value
    return (
        not satisfies_hard_constraints(metrics, evaluation_metrics),
        primary_key,
        float(metrics.get("avg_episode_length", metrics.get("episode_length", 0.0))),
    )


def _required_constraint_name(constraint: dict[str, Any]) -> str:
    name = constraint.get("name")
    if not name:
        raise ValueError("Hard constraint must define name")
    return str(name)
