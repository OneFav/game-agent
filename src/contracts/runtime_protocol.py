from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from contracts.visualization_protocol import VisualizationSpec


@dataclass(frozen=True)
class ScenarioDescriptor:
    """Static, renderer-independent description of one executable scenario."""

    scenario_id: str
    task_family: str
    capabilities: dict[str, Any]
    agents: tuple[str, ...]
    observation_spaces: dict[str, Any]
    action_spaces: dict[str, Any]
    disclosures: tuple[str, ...] = ()
    visualization: VisualizationSpec | None = None


@dataclass(frozen=True)
class ScenarioEvent:
    """One timestamped fact emitted by a scenario runtime."""

    event_type: str
    step: int
    time: float
    participants: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FramePacket:
    """Serializable dynamic frame consumed by replay and visualization clients."""

    scenario_time: float
    episode_step: int
    entities: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...] = ()
    fields: tuple[dict[str, Any], ...] = ()
    observations: dict[str, Any] = field(default_factory=dict)
    actions: dict[str, Any] = field(default_factory=dict)
    messages: tuple[dict[str, Any], ...] = ()
    events: tuple[ScenarioEvent, ...] = ()
    rewards: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    observations: dict[str, Any]
    rewards: dict[str, float]
    terminations: dict[str, bool]
    truncations: dict[str, bool]
    events: tuple[ScenarioEvent, ...]
    info: dict[str, Any]


@runtime_checkable
class ScenarioRuntime(Protocol):
    """Minimal runtime boundary shared by training, evaluation, and replay."""

    agents: list[str]

    def describe(self) -> ScenarioDescriptor:
        ...

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        ...

    def step(
        self, actions: dict[str, Any]
    ) -> tuple[
        dict[str, Any],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, Any],
    ]:
        ...

    def snapshot(self) -> FramePacket:
        ...

    def get_metrics(self) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...
