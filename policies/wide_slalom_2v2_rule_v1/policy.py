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
from game_agent.envs.swarm_combat.entities import Role
from game_agent.policy_designer.reference_policies.safe_rule_policy import SafeRulePolicy


AGENT_ORDER = ["red_racer_0", "red_defender_0", "blue_racer_0", "blue_defender_0"]
AGENT_TO_ID = {name: index for index, name in enumerate(AGENT_ORDER)}

DEFAULT_ENV_SPEC: dict[str, Any] = {
    "action_space": {
        "shape": [4],
        "low": [-1.0, -1.0, -1.0, -1.0],
        "high": [1.0, 1.0, 1.0, 1.0],
    },
    "observation_space": {"shape": [12]},
}


DEFAULT_CONFIG: dict[str, Any] = {
    "desired_speed": 4.5,
    "position_gain": 1.2,
    "velocity_gain": 2.2,
    "risk_margin": 0.75,
    "boundary_margin": 1.2,
    "turn_steps": 12,
    "turn_lookahead": 5.0,
    "risk_lookahead_steps": 18,
    "brake_release_speed": 0.35,
    "lane_spacing": 1.2,
    "gate_approach_offset": 4.0,
    "gate_exit_offset": 3.0,
    "separation_gain": 4.0,
    "reserved_action_value": 0.0,
}


class TeamAwareSafeRulePolicy(SafeRulePolicy):
    def _defender_target(self, env, drone) -> np.ndarray:
        if getattr(drone.team, "name", "") == "BLUE":
            opponents = [candidate for candidate in env.drones if candidate.team != drone.team and candidate.role == Role.RACER]
            if opponents:
                target = min(opponents, key=lambda other: np.linalg.norm(other.position - drone.position))
                return target.position
        return super()._defender_target(env, drone)


class PolicyClass(Policy):
    def __init__(self, config: dict[str, Any] | None = None, env_spec: dict[str, Any] | None = None) -> None:
        self.config = self._validated_config(config or {})
        self.env_spec = env_spec or DEFAULT_ENV_SPEC
        action_space = self.env_spec.get("action_space", DEFAULT_ENV_SPEC["action_space"])
        self._action_shape = tuple(action_space.get("shape", [4]))
        self._action_low = np.asarray(action_space.get("low", [-1.0, -1.0, -1.0, -1.0]), dtype=np.float32)
        self._action_high = np.asarray(action_space.get("high", [1.0, 1.0, 1.0, 1.0]), dtype=np.float32)
        if self._action_low.shape != (4,) or self._action_high.shape != (4,):
            self._action_low = np.full((4,), -1.0, dtype=np.float32)
            self._action_high = np.full((4,), 1.0, dtype=np.float32)
        self._policy = TeamAwareSafeRulePolicy(
            desired_speed=float(self.config["desired_speed"]),
            position_gain=float(self.config["position_gain"]),
            velocity_gain=float(self.config["velocity_gain"]),
            risk_margin=float(self.config["risk_margin"]),
            boundary_margin=float(self.config["boundary_margin"]),
            turn_steps=int(self.config["turn_steps"]),
            turn_lookahead=float(self.config["turn_lookahead"]),
            risk_lookahead_steps=int(self.config["risk_lookahead_steps"]),
            brake_release_speed=float(self.config["brake_release_speed"]),
            lane_spacing=float(self.config["lane_spacing"]),
            gate_approach_offset=float(self.config["gate_approach_offset"]),
            gate_exit_offset=float(self.config["gate_exit_offset"]),
            separation_gain=float(self.config["separation_gain"]),
            defender_mode="escort",
        )
        self._cached_step: int | None = None
        self._cached_actions: dict[str, np.ndarray] = {}
        self._seed = 0
        self._checkpoint_path: str | None = None
        self._needs_env_reset = True

    def reset(self, seed: int) -> None:
        self._seed = int(seed)
        self._cached_step = None
        self._cached_actions = {}
        self._needs_env_reset = True

    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        try:
            raw_env = info.get("raw_env") if isinstance(info, dict) else None
            if raw_env is not None:
                return self._act_from_env(raw_env, agent_id)
            return self._fallback_action(obs, agent_id)
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
            self.__init__(data["config"], self.env_spec)

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "desired_speed": {"type": "number", "minimum": 0.5, "maximum": 8.0, "default": 4.5},
            "position_gain": {"type": "number", "minimum": 0.1, "maximum": 5.0, "default": 1.2},
            "velocity_gain": {"type": "number", "minimum": 0.1, "maximum": 5.0, "default": 2.2},
            "risk_margin": {"type": "number", "minimum": 0.1, "maximum": 2.0, "default": 0.75},
            "boundary_margin": {"type": "number", "minimum": 0.5, "maximum": 3.0, "default": 1.2},
            "turn_steps": {"type": "integer", "minimum": 2, "maximum": 64, "default": 12},
            "turn_lookahead": {"type": "number", "minimum": 1.0, "maximum": 12.0, "default": 5.0},
            "risk_lookahead_steps": {"type": "integer", "minimum": 4, "maximum": 64, "default": 18},
            "brake_release_speed": {"type": "number", "minimum": 0.0, "maximum": 2.0, "default": 0.35},
            "lane_spacing": {"type": "number", "minimum": 0.2, "maximum": 3.0, "default": 1.2},
            "gate_approach_offset": {"type": "number", "minimum": 1.0, "maximum": 8.0, "default": 4.0},
            "gate_exit_offset": {"type": "number", "minimum": 1.0, "maximum": 8.0, "default": 3.0},
            "separation_gain": {"type": "number", "minimum": 0.5, "maximum": 8.0, "default": 4.0},
            "reserved_action_value": {"type": "number", "minimum": 0.0, "maximum": 0.0, "default": 0.0},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "seed": self._seed,
            "checkpoint_path": self._checkpoint_path,
            "policy_type": "TeamAwareSafeRulePolicy",
        }

    def _act_from_env(self, raw_env: Any, agent_id: str) -> np.ndarray:
        if self._needs_env_reset:
            self._policy.reset(raw_env)
            self._needs_env_reset = False
        current_step = int(getattr(raw_env, "step_count", 0))
        if self._cached_step != current_step or agent_id not in self._cached_actions:
            raw_actions = self._policy.compute_actions(raw_env)
            normalized: dict[str, np.ndarray] = {}
            for name, drone_id in AGENT_TO_ID.items():
                drone = next(drone for drone in raw_env.drones if drone.id == drone_id)
                max_accel = float(getattr(drone.dynamics, "max_accel", raw_env.cfg.drone.max_accel))
                command = np.asarray(raw_actions.get(drone_id, np.zeros(3, dtype=np.float32)), dtype=np.float32)
                command = np.clip(command / max(max_accel, 1e-6), -1.0, 1.0)
                action = np.array(
                    [command[0], command[1], command[2], float(self.config["reserved_action_value"])],
                    dtype=np.float32,
                )
                normalized[name] = self._clip_action(action)
            self._cached_step = current_step
            self._cached_actions = normalized
        return self._cached_actions[agent_id].copy()

    def _fallback_action(self, obs: Any, agent_id: str) -> np.ndarray:
        observation = self._extract_observation(obs, agent_id)
        command = np.zeros(3, dtype=np.float32)
        if observation.shape[0] >= 32:
            gate_direction = observation[17:19]
            nearest_opponent = observation[26:28]
            command[:2] = self._normalize_2d(gate_direction) * float(self.config["desired_speed"]) / 8.0
            command[:2] += self._avoidance_2d(nearest_opponent)
            if "defender" in agent_id:
                command[:2] *= 0.75
        elif observation.shape[0] >= 12:
            gate_direction = observation[9:11]
            nearest_opponent = observation[4:6]
            command[:2] = self._normalize_2d(gate_direction) * float(self.config["desired_speed"]) / 8.0
            command[:2] += self._avoidance_2d(nearest_opponent)
        action = np.array(
            [
                command[0],
                command[1],
                command[2],
                float(self.config["reserved_action_value"]),
            ],
            dtype=np.float32,
        )
        return self._clip_action(action)

    def _validated_config(self, overrides: dict[str, Any]) -> dict[str, Any]:
        schema = self.get_config_schema()
        config = dict(DEFAULT_CONFIG)
        config.update(overrides)
        for name, rule in schema.items():
            value = config.get(name, rule["default"])
            if rule["type"] == "integer":
                if not isinstance(value, (int, float)):
                    raise TypeError(f"{name} must be numeric")
                value = int(value)
            else:
                if not isinstance(value, (int, float)):
                    raise TypeError(f"{name} must be numeric")
                value = float(value)
            if value < rule["minimum"] or value > rule["maximum"]:
                raise ValueError(f"{name} outside schema range")
            config[name] = value
        return config

    def _extract_observation(self, obs: Any, agent_id: str) -> np.ndarray:
        value = obs.get(agent_id, obs) if isinstance(obs, dict) else obs
        observation = np.asarray(value, dtype=np.float32).reshape(-1)
        if observation.shape[0] < 12:
            padded = np.zeros(12, dtype=np.float32)
            padded[: observation.shape[0]] = observation
            return padded
        return observation

    def _avoidance_2d(self, opponent_position: np.ndarray) -> np.ndarray:
        distance = float(np.linalg.norm(opponent_position))
        radius = 3.0
        if distance >= radius or distance < 1e-6:
            return np.zeros(2, dtype=np.float32)
        strength = (1.0 - distance / radius) * 0.35
        return -self._normalize_2d(opponent_position) * strength

    def _normalize_2d(self, vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm < 1e-6:
            return np.zeros(2, dtype=np.float32)
        return (vector / norm).astype(np.float32)

    def _clip_action(self, action: np.ndarray) -> np.ndarray:
        shield = np.maximum(np.abs(self._action_high) * 1.2, 1e-6).astype(np.float32)
        shielded = np.clip(action, -shield, shield)
        return np.clip(shielded, self._action_low, self._action_high).astype(np.float32)
