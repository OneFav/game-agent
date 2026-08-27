from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contracts.runtime_protocol import ScenarioRuntime


RuntimeFactory = Callable[[dict[str, Any]], ScenarioRuntime]


class ScenarioRegistry:
    """Explicit runtime registry that keeps environment selection out of runners."""

    def __init__(self) -> None:
        self._factories: dict[str, RuntimeFactory] = {}

    def register(
        self,
        task_family: str,
        factory: RuntimeFactory,
        *,
        replace: bool = False,
    ) -> None:
        family = str(task_family).strip()
        if not family:
            raise ValueError("task_family must be non-empty")
        if family in self._factories and not replace:
            raise ValueError(f"runtime already registered: {family}")
        self._factories[family] = factory

    def create(self, spec: dict[str, Any]) -> ScenarioRuntime:
        family = str(spec.get("task_family", "drone_ring_game"))
        try:
            factory = self._factories[family]
        except KeyError as error:
            supported = ", ".join(sorted(self._factories))
            raise KeyError(
                f"unsupported scenario task_family: {family}; supported: {supported}"
            ) from error
        return factory(spec)

    def supported_families(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


registry = ScenarioRegistry()


def _create_drone_ring_runtime(spec: dict[str, Any]) -> ScenarioRuntime:
    from game_agent.scenarios.drone_ring_adapter import DroneRingRuntimeAdapter

    return DroneRingRuntimeAdapter(spec)


registry.register("drone_ring_game", _create_drone_ring_runtime)


def _create_representative_runtime(spec: dict[str, Any]) -> ScenarioRuntime:
    from game_agent.scenarios.representative import RepresentativeScenarioRuntime

    return RepresentativeScenarioRuntime(spec)


for _family in (
    "navigation",
    "dynamics",
    "pursuit_evasion",
    "team_cooperation",
    "escort_defense",
    "sensor_game",
    "communication_game",
    "robustness",
    "hybrid_mission",
    "scale_external",
):
    registry.register(_family, _create_representative_runtime)


def create_runtime(spec: dict[str, Any]) -> ScenarioRuntime:
    return registry.create(spec)
