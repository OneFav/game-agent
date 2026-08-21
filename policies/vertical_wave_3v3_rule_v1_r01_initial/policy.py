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
from game_agent.policy_designer.reference_policies.safe_rule_policy import SafeRulePolicy


DEFAULT_ENV_SPEC: dict[str, Any] = {
    "action_space": {"shape": [3], "low": [-10.0, -10.0, -10.0], "high": [10.0, 10.0, 10.0]},
    "observation_space": {"shape": [94]},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "red_desired_speed": 5.8,
    "blue_desired_speed": 5.8,
    "shared_position_gain": 1.3,
    "shared_velocity_gain": 2.2,
    "red_risk_margin": 0.9,
    "blue_risk_margin": 0.9,
    "shared_boundary_margin": 1.2,
    "shared_turn_steps": 12,
    "shared_turn_lookahead": 6.0,
    "shared_risk_lookahead_steps": 18,
    "shared_brake_release_speed": 0.35,
    "red_lane_spacing": 1.4,
    "blue_lane_spacing": 1.4,
    "shared_gate_approach_offset": 4.5,
    "shared_gate_exit_offset": 3.5,
    "shared_separation_gain": 4.5,
    "red_defender_mode": "escort",
    "blue_defender_mode": "intercept",
}


class RedPolicy:
    """Red-side behavior and parameters only."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.controller = _build_team_controller(config, "red")

    def compute_actions(self, env: Any) -> dict[int, np.ndarray]:
        return self.controller.compute_actions(env)


class BluePolicy:
    """Blue-side behavior and parameters only."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.controller = _build_team_controller(config, "blue")

    def compute_actions(self, env: Any) -> dict[int, np.ndarray]:
        return self.controller.compute_actions(env)


class VerticalWaveRulePolicy(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.env_spec = env_spec or DEFAULT_ENV_SPEC
        self.config = self._validated_config(config or {})
        action_space = self.env_spec.get("action_space", DEFAULT_ENV_SPEC["action_space"])
        self._action_low = np.asarray(action_space.get("low", DEFAULT_ENV_SPEC["action_space"]["low"]), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", DEFAULT_ENV_SPEC["action_space"]["high"]), dtype=np.float32)
        self._action_dim = int(action_space.get("shape", [len(self._action_low)])[0])
        if self._action_low.shape[0] != self._action_dim or self._action_high.shape[0] != self._action_dim:
            self._action_dim = min(len(self._action_low), len(self._action_high))
            self._action_low = self._action_low[: self._action_dim]
            self._action_high = self._action_high[: self._action_dim]
        self._seed = 0
        self._checkpoint_path: str | None = None
        self._red_policy = RedPolicy(self.config)
        self._blue_policy = BluePolicy(self.config)

    def reset(self, seed: int) -> None:
        self._seed = int(seed)
        self._red_policy = RedPolicy(self.config)
        self._blue_policy = BluePolicy(self.config)

    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        del info
        try:
            observation = self._extract_observation(obs, agent_id)
            command = self._fallback_action(observation, agent_id)
            return np.clip(command, self._action_low, self._action_high).astype(np.float32)
        except Exception:
            return np.zeros((self._action_dim,), dtype=np.float32)

    def compute_actions(self, env: Any) -> dict[Any, np.ndarray]:
        base_env = getattr(env, "base_env", env)
        red_actions = self._red_policy.compute_actions(base_env)
        blue_actions = self._blue_policy.compute_actions(base_env)
        raw_actions = {}
        for drone in base_env.drones:
            if getattr(drone.team, "name", "").lower() == "red":
                raw_actions[drone.id] = red_actions.get(drone.id, np.zeros(3, dtype=np.float32))
            else:
                raw_actions[drone.id] = blue_actions.get(drone.id, np.zeros(3, dtype=np.float32))
        if getattr(env, "agents", None) and isinstance(env.agents[0], str):
            actions: dict[str, np.ndarray] = {}
            for index, agent_id in enumerate(env.agents):
                raw = np.asarray(raw_actions.get(index, np.zeros(3, dtype=np.float32)), dtype=np.float32)
                actions[agent_id] = np.clip(raw[: self._action_dim], self._action_low, self._action_high).astype(np.float32)
            return actions
        return {
            agent_id: np.clip(np.asarray(action, dtype=np.float32)[: self._action_dim], self._action_low, self._action_high)
            for agent_id, action in raw_actions.items()
        }

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
            self._red_policy = RedPolicy(self.config)
            self._blue_policy = BluePolicy(self.config)

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "red_desired_speed": {"type": "number", "minimum": 2.0, "maximum": 8.0, "default": 5.8},
            "blue_desired_speed": {"type": "number", "minimum": 2.0, "maximum": 8.0, "default": 5.8},
            "shared_position_gain": {"type": "number", "minimum": 0.5, "maximum": 3.0, "default": 1.3},
            "shared_velocity_gain": {"type": "number", "minimum": 0.5, "maximum": 4.0, "default": 2.2},
            "red_risk_margin": {"type": "number", "minimum": 0.1, "maximum": 2.0, "default": 0.9},
            "blue_risk_margin": {"type": "number", "minimum": 0.1, "maximum": 2.0, "default": 0.9},
            "shared_boundary_margin": {"type": "number", "minimum": 0.4, "maximum": 3.0, "default": 1.2},
            "shared_turn_steps": {"type": "integer", "minimum": 2, "maximum": 40, "default": 12},
            "shared_turn_lookahead": {"type": "number", "minimum": 2.0, "maximum": 10.0, "default": 6.0},
            "shared_risk_lookahead_steps": {"type": "integer", "minimum": 4, "maximum": 40, "default": 18},
            "shared_brake_release_speed": {"type": "number", "minimum": 0.1, "maximum": 1.0, "default": 0.35},
            "red_lane_spacing": {"type": "number", "minimum": 0.6, "maximum": 2.2, "default": 1.4},
            "blue_lane_spacing": {"type": "number", "minimum": 0.6, "maximum": 2.2, "default": 1.4},
            "shared_gate_approach_offset": {"type": "number", "minimum": 2.0, "maximum": 8.0, "default": 4.5},
            "shared_gate_exit_offset": {"type": "number", "minimum": 1.0, "maximum": 6.0, "default": 3.5},
            "shared_separation_gain": {"type": "number", "minimum": 1.0, "maximum": 8.0, "default": 4.5},
            "red_defender_mode": {"type": "string", "enum": ["escort", "intercept"], "default": "escort"},
            "blue_defender_mode": {"type": "string", "enum": ["escort", "intercept"], "default": "intercept"},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "policy_family": "safe_rule_policy",
            "seed": self._seed,
            "checkpoint_path": self._checkpoint_path,
        }

    def _fallback_action(self, observation: np.ndarray, agent_id: str) -> np.ndarray:
        velocity = observation[3:6] if observation.shape[0] >= 6 else np.zeros(3, dtype=np.float32)
        first_gate_rel = observation[46:49] if observation.shape[0] >= 49 else np.zeros(3, dtype=np.float32)
        direction = self._normalize(first_gate_rel)
        if "defender" in agent_id:
            direction = 0.6 * direction - 0.4 * self._normalize(velocity)
        else:
            direction = direction - 0.2 * self._normalize(velocity)
        desired_speed = self.config["red_desired_speed"] if str(agent_id).startswith("red") else self.config["blue_desired_speed"]
        return direction.astype(np.float32) * min(float(desired_speed), float(self._action_high[0]))

    def _extract_observation(self, obs: Any, agent_id: str) -> np.ndarray:
        value = obs.get(agent_id, obs) if isinstance(obs, dict) else obs
        observation = np.asarray(value, dtype=np.float32).reshape(-1)
        if observation.shape[0] >= 94:
            return observation
        padded = np.zeros(94, dtype=np.float32)
        padded[: observation.shape[0]] = observation
        return padded

    def _validated_config(self, overrides: dict[str, Any]) -> dict[str, Any]:
        schema = self.get_config_schema()
        config = dict(DEFAULT_CONFIG)
        config.update(overrides)
        for name, rule in schema.items():
            value = config.get(name, rule["default"])
            if rule["type"] == "string":
                if value not in rule["enum"]:
                    raise ValueError(f"{name} outside enum")
                config[name] = value
                continue
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            numeric = int(value) if rule["type"] == "integer" else float(value)
            if numeric < rule["minimum"] or numeric > rule["maximum"]:
                raise ValueError(f"{name} outside schema range")
            config[name] = numeric
        return config

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return np.zeros(3, dtype=np.float32)
        return (vector / norm).astype(np.float32)


PolicyClass = VerticalWaveRulePolicy


def _build_team_controller(config: dict[str, Any], side: str) -> SafeRulePolicy:
    return SafeRulePolicy(
        desired_speed=float(config[f"{side}_desired_speed"]),
        position_gain=float(config["shared_position_gain"]),
        velocity_gain=float(config["shared_velocity_gain"]),
        risk_margin=float(config[f"{side}_risk_margin"]),
        boundary_margin=float(config["shared_boundary_margin"]),
        turn_steps=int(config["shared_turn_steps"]),
        turn_lookahead=float(config["shared_turn_lookahead"]),
        risk_lookahead_steps=int(config["shared_risk_lookahead_steps"]),
        brake_release_speed=float(config["shared_brake_release_speed"]),
        lane_spacing=float(config[f"{side}_lane_spacing"]),
        gate_approach_offset=float(config["shared_gate_approach_offset"]),
        gate_exit_offset=float(config["shared_gate_exit_offset"]),
        separation_gain=float(config["shared_separation_gain"]),
        defender_mode=str(config[f"{side}_defender_mode"]),
    )
