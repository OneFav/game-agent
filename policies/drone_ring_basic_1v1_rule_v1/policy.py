from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np


def _add_project_root_to_sys_path() -> None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "contracts").exists() or (candidate / "game_agent").exists():
            sys.path.insert(0, str(candidate))
            return


_add_project_root_to_sys_path()

try:
    from contracts.policy_protocol import Policy
except ModuleNotFoundError:
    from abc import ABC, abstractmethod

    class Policy(ABC):
        @abstractmethod
        def reset(self, seed: int) -> None:
            pass

        @abstractmethod
        def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
            pass

        @abstractmethod
        def load(self, checkpoint_path: str) -> None:
            pass

        @abstractmethod
        def get_config_schema(self) -> dict[str, Any]:
            pass

        def supports_training(self) -> bool:
            return True

        def get_diagnostics(self) -> dict[str, Any]:
            return {}


class RuleRingNavigationPolicy(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        env_spec = env_spec or {}
        action_space = env_spec.get("action_space", {})
        self._action_low = np.asarray(action_space.get("low", [-2.0, -2.0, -1.0, -1.0]), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", [2.0, 2.0, 1.0, 1.0]), dtype=np.float32)
        self._speed_scale = float(self.config.get("speed_scale", 1.0))
        self._intercept_gain = float(self.config.get("intercept_gain", 1.0))
        self._safety_margin = float(self.config.get("safety_margin", 0.2))
        self._seed: int | None = None
        self._checkpoint_path: str | None = None

    def reset(self, seed: int) -> None:
        self._seed = int(seed)

    def act(self, obs: Any, agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        del info
        observation = np.asarray(obs[agent_id] if isinstance(obs, dict) else obs, dtype=np.float32)
        if agent_id.startswith("red"):
            direction = observation[9:11]
            opponent_offset = observation[4:6]
            opponent_distance = float(np.linalg.norm(opponent_offset))
            if opponent_distance < self._safety_margin:
                avoidance = -self._normalize(opponent_offset)
                weight = 1.0 - opponent_distance / max(self._safety_margin, 1e-6)
                direction = direction + avoidance * weight
            gain = self._speed_scale
        else:
            direction = observation[6:8]
            gain = self._intercept_gain

        velocity = self._normalize(direction) * gain
        action = np.array([velocity[0], velocity[1], 0.0, 0.0], dtype=np.float32)
        return np.clip(action, self._action_low, self._action_high).astype(np.float32)

    def load(self, checkpoint_path: str) -> None:
        self._checkpoint_path = str(Path(checkpoint_path))

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "speed_scale": {"type": "number", "default": 1.0},
            "intercept_gain": {"type": "number", "default": 1.0},
            "safety_margin": {"type": "number", "default": 0.2},
        }

    def get_diagnostics(self) -> dict[str, Any]:
        return {"seed": self._seed, "checkpoint_path": self._checkpoint_path}

    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return np.zeros(2, dtype=np.float32)
        return (vector / norm).astype(np.float32)


PolicyClass = RuleRingNavigationPolicy
