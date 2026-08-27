from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any


class ResearchStage(IntEnum):
    """AutoResearch 的最小可用修改层级。"""

    PARAMETERS = 1
    RECIPE = 2
    POLICY_CODE = 3


_CAPABILITIES: dict[ResearchStage, tuple[str, ...]] = {
    ResearchStage.PARAMETERS: ("existing_parameter_search",),
    ResearchStage.RECIPE: (
        "existing_parameter_search",
        "training_recipe_change",
        "search_space_extension",
    ),
    ResearchStage.POLICY_CODE: (
        "existing_parameter_search",
        "training_recipe_change",
        "search_space_extension",
        "policy_local_code_change",
    ),
}


@dataclass(frozen=True)
class StageTransition:
    previous: int
    current: int
    succeeded: bool
    reason: str


@dataclass
class ResearchState:
    """记录阶段级结果，而不是对每个单独 trial 升降级。"""

    stage: ResearchStage = ResearchStage.PARAMETERS
    history: list[StageTransition] = field(default_factory=list)

    @property
    def enabled_capabilities(self) -> tuple[str, ...]:
        return _CAPABILITIES[self.stage]

    def record_stage_result(self, *, succeeded: bool, reason: str) -> StageTransition:
        """失败升一级，成功降一级，并始终限制在 1..3。"""

        previous = self.stage
        delta = -1 if succeeded else 1
        next_value = min(
            int(ResearchStage.POLICY_CODE),
            max(int(ResearchStage.PARAMETERS), int(previous) + delta),
        )
        self.stage = ResearchStage(next_value)
        transition = StageTransition(
            previous=int(previous),
            current=int(self.stage),
            succeeded=succeeded,
            reason=reason,
        )
        self.history.append(transition)
        return transition

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "stage": int(self.stage),
            "enabled_capabilities": list(self.enabled_capabilities),
            "history": [asdict(item) for item in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchState:
        stage = ResearchStage(int(data.get("stage", ResearchStage.PARAMETERS)))
        raw_history = data.get("history", [])
        if not isinstance(raw_history, list):
            raise ValueError("history must be a list")
        history = [
            StageTransition(
                previous=int(item["previous"]),
                current=int(item["current"]),
                succeeded=bool(item["succeeded"]),
                reason=str(item.get("reason", "")),
            )
            for item in raw_history
        ]
        return cls(stage=stage, history=history)
