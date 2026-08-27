from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def _add_project_root_to_sys_path() -> None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "contracts").exists() or (candidate / "src" / "contracts").exists():
            sys.path.insert(0, str(candidate))
            src_path = candidate / "src"
            if src_path.exists():
                sys.path.insert(0, str(src_path))
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


class RuleRingNavigationPolicy(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        env_spec = env_spec or {}
        action_space = env_spec.get("action_space", {})
        self._action_low = np.asarray(action_space.get("low", [-2.0, -2.0, -1.0, -1.0]), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", [2.0, 2.0, 1.0, 1.0]), dtype=np.float32)

        self._speed_scale = float(self.config.get("speed_scale", 1.2))
        self._intercept_gain = float(self.config.get("intercept_gain", 0.75))
        self._safety_margin = float(self.config.get("safety_margin", 0.9))
        self._blue_gate_bias = float(self.config.get("blue_gate_bias", 0.3))
        self._memory_decay = float(self.config.get("memory_decay", 0.85))
        self._recovery_gain = float(self.config.get("recovery_gain", 1.1))

        self._seed: int | None = None
        self._checkpoint_path: str | None = None
        self._memory: dict[tuple[str, str], np.ndarray] = {}
        self._loaded_checkpoint_config: dict[str, Any] | None = None

    def reset(self, seed: int) -> None:
        self._seed = int(seed)
        self._memory.clear()

    def act(self, obs: Any, agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        del info
        try:
            observation = np.asarray(obs[agent_id] if isinstance(obs, dict) else obs, dtype=np.float32)
            own_velocity = self._slice(observation, 2, 4)
            opponent_offset = self._remember(agent_id, "opponent_offset", self._slice(observation, 4, 6))
            opponent_rel_velocity = self._remember(agent_id, "opponent_rel_velocity", self._slice(observation, 6, 8))
            progress = float(observation[8]) if observation.size > 8 else 1.0
            target_direction = self._remember(
                agent_id,
                "target_direction",
                self._slice(observation, 9, 11),
                fallback=np.array([1.0, 0.0], dtype=np.float32),
            )
            target_distance = float(observation[11]) if observation.size > 11 else 0.0

            if agent_id.startswith("red"):
                desired_velocity = self._red_desired_velocity(
                    agent_id=agent_id,
                    own_velocity=own_velocity,
                    opponent_offset=opponent_offset,
                    target_direction=target_direction,
                    progress=progress,
                    target_distance=target_distance,
                )
            else:
                desired_velocity = self._blue_desired_velocity(
                    agent_id=agent_id,
                    own_velocity=own_velocity,
                    opponent_offset=opponent_offset,
                    opponent_rel_velocity=opponent_rel_velocity,
                    target_direction=target_direction,
                )

            acceleration = (desired_velocity - own_velocity) * self._recovery_gain
            action = np.array([acceleration[0], acceleration[1], 0.0, 0.0], dtype=np.float32)
            return np.clip(action, self._action_low, self._action_high).astype(np.float32)
        except Exception:
            return np.clip(np.zeros(4, dtype=np.float32), self._action_low, self._action_high).astype(np.float32)

    def load(self, checkpoint_path: str) -> None:
        self._checkpoint_path = str(Path(checkpoint_path))
        path = Path(checkpoint_path)
        if not path.is_file():
            self._loaded_checkpoint_config = None
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._loaded_checkpoint_config = None
            return
        if isinstance(payload, dict) and isinstance(payload.get("config"), dict):
            self._loaded_checkpoint_config = dict(payload["config"])

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "speed_scale": {"type": "number", "default": 1.2, "minimum": 0.4, "maximum": 2.0},
            "intercept_gain": {"type": "number", "default": 0.75, "minimum": 0.1, "maximum": 2.0},
            "safety_margin": {"type": "number", "default": 0.9, "minimum": 0.1, "maximum": 3.0},
            "blue_gate_bias": {"type": "number", "default": 0.3, "minimum": 0.0, "maximum": 1.5},
            "memory_decay": {"type": "number", "default": 0.85, "minimum": 0.0, "maximum": 1.0},
            "recovery_gain": {"type": "number", "default": 1.1, "minimum": 0.1, "maximum": 2.0},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "seed": self._seed,
            "checkpoint_path": self._checkpoint_path,
            "loaded_checkpoint_config": self._loaded_checkpoint_config,
        }

    def _red_desired_velocity(
        self,
        agent_id: str,
        own_velocity: np.ndarray,
        opponent_offset: np.ndarray,
        target_direction: np.ndarray,
        progress: float,
        target_distance: float,
    ) -> np.ndarray:
        del own_velocity
        target_unit = self._normalize(target_direction, fallback=np.array([1.0, 0.0], dtype=np.float32))
        opponent_distance = float(np.linalg.norm(opponent_offset))

        forward_weight = 1.0 + (1.0 - progress) * 0.35
        steering = target_unit * forward_weight
        if target_distance > 1e-6:
            steering = steering + target_unit * min(target_distance / 8.0, 0.35)

        if 1e-6 < opponent_distance < self._safety_margin * 1.6:
            threat = self._normalize(opponent_offset)
            clearance = (self._safety_margin * 1.6 - opponent_distance) / max(self._safety_margin * 1.6, 1e-6)
            tangent = self._orthogonal(target_unit, threat)
            steering = steering - threat * (0.9 * clearance) + tangent * (0.45 * clearance)

        desired_velocity = self._normalize(steering, fallback=target_unit) * self._speed_scale
        self._memory[(agent_id, "red_velocity")] = desired_velocity.astype(np.float32)
        return desired_velocity.astype(np.float32)

    def _blue_desired_velocity(
        self,
        agent_id: str,
        own_velocity: np.ndarray,
        opponent_offset: np.ndarray,
        opponent_rel_velocity: np.ndarray,
        target_direction: np.ndarray,
    ) -> np.ndarray:
        del own_velocity
        target_unit = self._normalize(target_direction, fallback=np.array([1.0, 0.0], dtype=np.float32))
        predicted_offset = opponent_offset + opponent_rel_velocity * 0.65
        pursuit = self._normalize(predicted_offset, fallback=target_unit)
        steering = pursuit * self._intercept_gain + target_unit * self._blue_gate_bias

        opponent_distance = float(np.linalg.norm(opponent_offset))
        if 1e-6 < opponent_distance < self._safety_margin * 0.9:
            steering = steering - self._normalize(opponent_offset) * 0.75

        desired_speed = max(self._speed_scale * 0.88, 0.7)
        desired_velocity = self._normalize(steering, fallback=pursuit) * desired_speed
        self._memory[(agent_id, "blue_velocity")] = desired_velocity.astype(np.float32)
        return desired_velocity.astype(np.float32)

    def _remember(
        self,
        agent_id: str,
        key: str,
        value: np.ndarray,
        fallback: np.ndarray | None = None,
    ) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float32)
        memory_key = (agent_id, key)
        if float(np.linalg.norm(vector)) > 1e-6:
            self._memory[memory_key] = vector.astype(np.float32)
            return vector.astype(np.float32)

        previous = self._memory.get(memory_key)
        if previous is not None:
            decayed = (previous * self._memory_decay).astype(np.float32)
            self._memory[memory_key] = decayed
            return decayed

        if fallback is None:
            return np.zeros(2, dtype=np.float32)
        return np.asarray(fallback, dtype=np.float32)

    def _slice(self, observation: np.ndarray, start: int, end: int) -> np.ndarray:
        if observation.size < end:
            return np.zeros(end - start, dtype=np.float32)
        return observation[start:end].astype(np.float32)

    def _normalize(self, vector: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            if fallback is None:
                return np.zeros(2, dtype=np.float32)
            fallback_norm = float(np.linalg.norm(fallback))
            if fallback_norm < 1e-6:
                return np.zeros(2, dtype=np.float32)
            return (fallback / fallback_norm).astype(np.float32)
        return (vector / norm).astype(np.float32)

    def _orthogonal(self, forward: np.ndarray, threat: np.ndarray) -> np.ndarray:
        forward_unit = self._normalize(forward, fallback=np.array([1.0, 0.0], dtype=np.float32))
        left = np.array([-forward_unit[1], forward_unit[0]], dtype=np.float32)
        right = -left
        return left if float(np.dot(left, threat)) < float(np.dot(right, threat)) else right


PolicyClass = RuleRingNavigationPolicy
