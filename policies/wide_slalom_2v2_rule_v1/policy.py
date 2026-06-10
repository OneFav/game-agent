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
    "action_space": {
        "shape": [4],
        "low": [-1.0, -1.0, -1.0, -1.0],
        "high": [1.0, 1.0, 1.0, 1.0],
    },
    "observation_space": {"shape": [12]},
}


DEFAULT_CONFIG: dict[str, float] = {
    "racer_gain": 0.92,
    "escort_gain": 0.72,
    "intercept_gain": 0.95,
    "block_gain": 0.62,
    "avoidance_radius": 2.5,
    "avoidance_gain": 0.45,
    "velocity_damping": 0.10,
    "prediction_horizon": 0.35,
    "reserved_action_value": 0.0,
}


class RuleWideSlalom2v2Policy(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.config = self._validated_config(config or {})
        env_spec = env_spec or DEFAULT_ENV_SPEC
        action_space = env_spec.get("action_space", DEFAULT_ENV_SPEC["action_space"])
        self._action_shape = tuple(action_space.get("shape", [4]))
        self._action_low = np.asarray(action_space.get("low", [-1.0] * 4), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", [1.0] * 4), dtype=np.float32)
        if self._action_low.shape != (4,) or self._action_high.shape != (4,):
            self._action_low = np.full((4,), -1.0, dtype=np.float32)
            self._action_high = np.full((4,), 1.0, dtype=np.float32)
        self._seed = 0
        self._checkpoint_path: str | None = None

    def reset(self, seed: int) -> None:
        self._seed = int(seed)

    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        del info
        try:
            observation = self._extract_observation(obs, agent_id)
            command = self._role_command(observation, agent_id)
            action = np.array(
                [
                    command[0],
                    command[1],
                    self.config["reserved_action_value"],
                    self.config["reserved_action_value"],
                ],
                dtype=np.float32,
            )
            shield = np.maximum(np.abs(self._action_high) * 1.2, 1e-6).astype(np.float32)
            shielded = np.clip(action, -shield, shield)
            return np.clip(shielded, self._action_low, self._action_high).astype(np.float32)
        except Exception:
            return np.zeros((4,), dtype=np.float32)

    def load(self, checkpoint_path: str) -> None:
        self._checkpoint_path = str(Path(checkpoint_path))
        path = Path(checkpoint_path)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, dict) and isinstance(data.get("config"), dict):
            self.config = self._validated_config(data["config"])

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "racer_gain": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.92},
            "escort_gain": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.72},
            "intercept_gain": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.95},
            "block_gain": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.62},
            "avoidance_radius": {"type": "number", "minimum": 0.5, "maximum": 6.0, "default": 2.5},
            "avoidance_gain": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.45},
            "velocity_damping": {"type": "number", "minimum": 0.0, "maximum": 0.5, "default": 0.10},
            "prediction_horizon": {"type": "number", "minimum": 0.0, "maximum": 1.5, "default": 0.35},
            "reserved_action_value": {"type": "number", "minimum": 0.0, "maximum": 0.0, "default": 0.0},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {"seed": self._seed, "checkpoint_path": self._checkpoint_path, "family": "rule_based"}

    def _role_command(self, observation: np.ndarray, agent_id: str) -> np.ndarray:
        parsed = self._parse_observation(observation)
        self_velocity = parsed["self_velocity"]
        opponent_position = parsed["nearest_opponent_position"]
        opponent_velocity = parsed["nearest_opponent_velocity"]
        gate_direction = parsed["gate_direction"]

        if agent_id == "red_racer_0":
            desired = self._normalize(gate_direction) * self.config["racer_gain"]
            desired += self._avoidance(opponent_position)
        elif agent_id == "red_defender_0":
            lateral = np.array([-gate_direction[1], gate_direction[0]], dtype=np.float32)
            desired = self._normalize(gate_direction + 0.35 * self._normalize(lateral)) * self.config["escort_gain"]
            desired += 0.5 * self._avoidance(opponent_position)
        elif agent_id == "blue_defender_0":
            intercept_point = opponent_position + opponent_velocity * self.config["prediction_horizon"]
            desired = self._normalize(intercept_point) * self.config["intercept_gain"]
        elif agent_id == "blue_racer_0":
            lateral = self._lane_offset(gate_direction, agent_id)
            route = self._normalize(gate_direction + 0.65 * lateral) * 0.75
            spacing = self._avoidance(opponent_position) * 1.4
            desired = self._normalize(route + spacing) * self.config["block_gain"]
        else:
            desired = self._normalize(gate_direction) * self.config["racer_gain"]

        desired -= self_velocity * self.config["velocity_damping"]
        return desired.astype(np.float32)

    def _parse_observation(self, observation: np.ndarray) -> dict[str, np.ndarray]:
        if observation.shape[0] >= 32:
            return {
                "self_velocity": observation[2:4],
                "nearest_opponent_position": observation[26:28],
                "nearest_opponent_velocity": observation[28:30],
                "gate_direction": observation[17:19],
            }
        return {
            "self_velocity": observation[2:4],
            "nearest_opponent_position": observation[4:6],
            "nearest_opponent_velocity": observation[6:8],
            "gate_direction": observation[9:11],
        }

    def _avoidance(self, opponent_position: np.ndarray) -> np.ndarray:
        distance = float(np.linalg.norm(opponent_position))
        radius = self.config["avoidance_radius"]
        if distance >= radius or distance < 1e-6:
            return np.zeros(2, dtype=np.float32)
        strength = (1.0 - distance / radius) * self.config["avoidance_gain"]
        return -self._normalize(opponent_position) * strength

    def _lane_offset(self, gate_direction: np.ndarray, agent_id: str) -> np.ndarray:
        direction = self._normalize(gate_direction)
        lateral = np.array([-direction[1], direction[0]], dtype=np.float32)
        if agent_id.startswith("blue"):
            lateral = -lateral
        return lateral

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

    def _normalize(self, vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return np.zeros(2, dtype=np.float32)
        return (vector / norm).astype(np.float32)


PolicyClass = RuleWideSlalom2v2Policy
