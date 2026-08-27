from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def _add_src_to_path() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        src = parent / "src"
        if (src / "contracts" / "policy_protocol.py").is_file():
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            return


_add_src_to_path()

from contracts.policy_protocol import Policy


DEFAULT_ENV_SPEC: dict[str, Any] = {
    "action_space": {"shape": [3], "low": [-1.0, -1.0, -1.0], "high": [1.0, 1.0, 1.0]},
    "observation_space": {"shape": [64]},
}

DEFAULT_CONFIG: dict[str, float] = {
    "racer_gain": 0.82,
    "intercept_gain": 0.74,
    "avoidance_gain": 0.46,
    "boundary_gain": 0.58,
    "prediction_horizon": 0.55,
    "velocity_damping": 0.18,
    "brake_bias": 0.25,
}


class Slalom1v13DRulePolicy(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.config = self._validated_config(config or {})
        self.env_spec = env_spec or DEFAULT_ENV_SPEC
        action_space = self.env_spec.get("action_space", DEFAULT_ENV_SPEC["action_space"])
        self._action_shape = tuple(int(v) for v in action_space.get("shape", [3]))
        self._action_low = np.asarray(action_space.get("low", [-1.0] * max(self._action_shape[0], 3)), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", [1.0] * max(self._action_shape[0], 3)), dtype=np.float32)
        self._seed = 0
        self._checkpoint_path: str | None = None

    def reset(self, seed: int) -> None:
        self._seed = int(seed)

    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        del info
        try:
            observation = self._extract_observation(obs, agent_id)
            command3 = self._role_command(observation, agent_id)
            action_dim = max(self._action_shape[0], 3)
            action = np.zeros(action_dim, dtype=np.float32)
            action[:3] = command3
            low = self._fit_bounds(self._action_low, action_dim, fill=-1.0)
            high = self._fit_bounds(self._action_high, action_dim, fill=1.0)
            return np.clip(action, low, high).astype(np.float32)
        except Exception:
            return np.zeros(max(self._action_shape[0], 3), dtype=np.float32)

    def load(self, checkpoint_path: str) -> None:
        self._checkpoint_path = str(Path(checkpoint_path))
        path = Path(checkpoint_path)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        config = data.get("config")
        if isinstance(config, dict):
            self.config = self._validated_config(config)

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "racer_gain": {"type": "number", "minimum": 0.4, "maximum": 1.2, "default": 0.82},
            "intercept_gain": {"type": "number", "minimum": 0.2, "maximum": 1.2, "default": 0.74},
            "avoidance_gain": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.46},
            "boundary_gain": {"type": "number", "minimum": 0.0, "maximum": 1.2, "default": 0.58},
            "prediction_horizon": {"type": "number", "minimum": 0.0, "maximum": 1.5, "default": 0.55},
            "velocity_damping": {"type": "number", "minimum": 0.0, "maximum": 0.6, "default": 0.18},
            "brake_bias": {"type": "number", "minimum": 0.0, "maximum": 0.6, "default": 0.25},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "seed": self._seed,
            "checkpoint_path": self._checkpoint_path,
            "algorithm_family": "rule_based",
        }

    def _role_command(self, observation: np.ndarray, agent_id: str) -> np.ndarray:
        parsed = self._parse_observation(observation)
        velocity = parsed["self_velocity"]
        target_vector = parsed["target_vector"]
        opponent_position = parsed["opponent_rel_position"]
        opponent_velocity = parsed["opponent_rel_velocity"]
        field_margin = parsed["field_margin"]
        self_position = parsed["self_position"]
        own_score = parsed["own_score"]

        if agent_id.startswith("red"):
            if own_score >= 1.0:
                retreat = np.array([-opponent_position[0], -opponent_position[1], 1.5], dtype=np.float32)
                desired = self._normalize(retreat) * (self.config["racer_gain"] * 0.6)
            else:
                desired = self._normalize(target_vector) * self.config["racer_gain"]
                desired += self._avoidance(opponent_position, opponent_velocity)
        else:
            intercept_point = opponent_position + opponent_velocity * self.config["prediction_horizon"]
            forward = self._normalize(target_vector)
            if float(np.linalg.norm(forward)) < 1e-6:
                forward = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            lateral = self._normalize(np.cross(forward, np.array([0.0, 0.0, 1.0], dtype=np.float32)))
            if float(np.linalg.norm(lateral)) < 1e-6:
                lateral = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            standoff = 1.4 if float(np.linalg.norm(opponent_position)) < 3.0 else 0.8
            desired = self._normalize(
                intercept_point
                + lateral * (0.9 + self.config["brake_bias"])
                + np.array([0.0, 0.0, standoff], dtype=np.float32)
            ) * self.config["intercept_gain"]
            if float(np.linalg.norm(opponent_position)) < 2.0:
                desired = self._normalize(lateral + np.array([0.0, 0.0, 1.0], dtype=np.float32)) * max(
                    self.config["intercept_gain"] * 0.6,
                    0.35,
                )
            desired += 0.8 * self._avoidance(opponent_position, opponent_velocity)

        boundary_push = self._boundary_push(self_position, field_margin)
        desired += boundary_push
        desired -= velocity * self.config["velocity_damping"]
        return desired.astype(np.float32)

    def _parse_observation(self, observation: np.ndarray) -> dict[str, np.ndarray | float]:
        if observation.shape[0] >= 30:
            return {
                "self_position": observation[0:3],
                "self_velocity": observation[3:6],
                "opponent_rel_position": observation[6:9],
                "opponent_rel_velocity": observation[9:12],
                "target_vector": observation[12:15],
                "field_margin": float(observation[25]),
                "own_score": float(observation[20]),
            }

        padded = np.zeros(15, dtype=np.float32)
        padded[: min(observation.shape[0], 15)] = observation[: min(observation.shape[0], 15)]
        return {
            "self_position": np.array([padded[0], padded[1], 4.0], dtype=np.float32),
            "self_velocity": np.array([padded[2], padded[3], 0.0], dtype=np.float32),
            "opponent_rel_position": np.array([padded[4], padded[5], 0.0], dtype=np.float32),
            "opponent_rel_velocity": np.array([padded[6], padded[7], 0.0], dtype=np.float32),
            "target_vector": np.array([padded[9], padded[10], 0.0], dtype=np.float32),
            "field_margin": 1.0,
            "own_score": 0.0,
        }

    def _avoidance(self, opponent_position: np.ndarray, opponent_velocity: np.ndarray) -> np.ndarray:
        predicted = opponent_position + opponent_velocity * self.config["prediction_horizon"]
        distance = float(np.linalg.norm(predicted))
        if distance < 1e-6 or distance > 6.0:
            return np.zeros(3, dtype=np.float32)
        strength = (1.0 - distance / 6.0) * self.config["avoidance_gain"]
        return -self._normalize(predicted) * strength

    def _boundary_push(self, self_position: np.ndarray, field_margin: float) -> np.ndarray:
        if field_margin >= 0.18:
            return np.zeros(3, dtype=np.float32)
        center_seek = -self._normalize(self_position)
        strength = (0.18 - field_margin) / 0.18
        return center_seek * self.config["boundary_gain"] * strength

    def _extract_observation(self, obs: Any, agent_id: str) -> np.ndarray:
        value = obs.get(agent_id, obs) if isinstance(obs, dict) else obs
        observation = np.asarray(value, dtype=np.float32).reshape(-1)
        if observation.shape[0] < 12:
            padded = np.zeros(12, dtype=np.float32)
            padded[: observation.shape[0]] = observation
            return padded
        return observation

    def _validated_config(self, overrides: dict[str, Any]) -> dict[str, float]:
        schema = self.get_config_schema()
        config = dict(DEFAULT_CONFIG)
        config.update(overrides)
        for name, rule in schema.items():
            value = config.get(name, rule["default"])
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            value = float(value)
            if value < float(rule["minimum"]) or value > float(rule["maximum"]):
                raise ValueError(f"{name} outside schema range")
            config[name] = value
        return config

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return np.zeros_like(vector, dtype=np.float32)
        return (vector / norm).astype(np.float32)

    @staticmethod
    def _fit_bounds(bounds: np.ndarray, size: int, fill: float) -> np.ndarray:
        bounds = np.asarray(bounds, dtype=np.float32).reshape(-1)
        if bounds.shape[0] >= size:
            return bounds[:size]
        padded = np.full(size, fill, dtype=np.float32)
        padded[: bounds.shape[0]] = bounds
        return padded


PolicyClass = Slalom1v13DRulePolicy
