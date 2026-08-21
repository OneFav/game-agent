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
    "red_desired_speed": 6.4,
    "blue_desired_speed": 7.0,
    "shared_position_gain": 1.3,
    "shared_velocity_gain": 2.2,
    "red_risk_margin": 0.8,
    "blue_risk_margin": 1.1,
    "shared_boundary_margin": 1.2,
    "shared_turn_steps": 12,
    "shared_turn_lookahead": 6.0,
    "shared_risk_lookahead_steps": 18,
    "shared_brake_release_speed": 0.35,
    "red_lane_spacing": 1.6,
    "blue_lane_spacing": 1.7,
    "shared_gate_approach_offset": 4.5,
    "shared_gate_exit_offset": 3.5,
    "shared_separation_gain": 4.5,
    "red_defender_mode": "escort",
    "blue_defender_mode": "intercept",
    "blue_intercept_gain": 2.6,
    "blue_intercept_radius": 7.0,
    "blue_pressure_buffer": 0.7,
}

FROZEN_ROUND3_CONFIG: dict[str, Any] = {
    "red_desired_speed": 6.4,
    "red_risk_margin": 0.8,
    "red_lane_spacing": 1.6,
    "red_defender_mode": "escort",
    "shared_position_gain": 1.3,
    "shared_velocity_gain": 2.2,
    "shared_boundary_margin": 1.2,
    "shared_turn_steps": 12,
    "shared_turn_lookahead": 6.0,
    "shared_risk_lookahead_steps": 18,
    "shared_brake_release_speed": 0.35,
    "shared_gate_approach_offset": 4.5,
    "shared_gate_exit_offset": 3.5,
    "shared_separation_gain": 4.5,
}


class RedPolicy:
    """Frozen Round-3 red-side opponent behavior and parameters only."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.controller = _build_team_controller(config, "red")

    def compute_actions(self, env: Any) -> dict[int, np.ndarray]:
        actions = self.controller.compute_actions(env)
        return _apply_red_inter_team_buffer(env, actions, self.config)


class BluePolicy:
    """Round-4 blue-side best response behavior and parameters only."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.controller = _build_team_controller(config, "blue")

    def compute_actions(self, env: Any) -> dict[int, np.ndarray]:
        actions = self.controller.compute_actions(env)
        actions = _apply_blue_racer_gate_drive(env, actions, self.config, self.controller)
        actions = _apply_blue_intercept_pressure(env, actions, self.config)
        return _apply_blue_defender_gate_frame_guard(env, actions, self.config)


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
            "red_desired_speed": {"type": "number", "minimum": 6.4, "maximum": 6.4, "default": 6.4},
            "blue_desired_speed": {"type": "number", "minimum": 6.4, "maximum": 7.6, "default": 7.0},
            "shared_position_gain": {"type": "number", "minimum": 1.3, "maximum": 1.3, "default": 1.3},
            "shared_velocity_gain": {"type": "number", "minimum": 2.2, "maximum": 2.2, "default": 2.2},
            "red_risk_margin": {"type": "number", "minimum": 0.8, "maximum": 0.8, "default": 0.8},
            "blue_risk_margin": {"type": "number", "minimum": 0.8, "maximum": 1.4, "default": 1.1},
            "shared_boundary_margin": {"type": "number", "minimum": 1.2, "maximum": 1.2, "default": 1.2},
            "shared_turn_steps": {"type": "integer", "minimum": 12, "maximum": 12, "default": 12},
            "shared_turn_lookahead": {"type": "number", "minimum": 6.0, "maximum": 6.0, "default": 6.0},
            "shared_risk_lookahead_steps": {"type": "integer", "minimum": 18, "maximum": 18, "default": 18},
            "shared_brake_release_speed": {"type": "number", "minimum": 0.35, "maximum": 0.35, "default": 0.35},
            "red_lane_spacing": {"type": "number", "minimum": 1.6, "maximum": 1.6, "default": 1.6},
            "blue_lane_spacing": {"type": "number", "minimum": 1.4, "maximum": 2.0, "default": 1.7},
            "shared_gate_approach_offset": {"type": "number", "minimum": 4.5, "maximum": 4.5, "default": 4.5},
            "shared_gate_exit_offset": {"type": "number", "minimum": 3.5, "maximum": 3.5, "default": 3.5},
            "shared_separation_gain": {"type": "number", "minimum": 4.5, "maximum": 4.5, "default": 4.5},
            "red_defender_mode": {"type": "string", "enum": ["escort"], "default": "escort"},
            "blue_defender_mode": {"type": "string", "enum": ["escort", "intercept"], "default": "intercept"},
            "blue_intercept_gain": {"type": "number", "minimum": 1.4, "maximum": 3.4, "default": 2.6},
            "blue_intercept_radius": {"type": "number", "minimum": 4.0, "maximum": 9.0, "default": 7.0},
            "blue_pressure_buffer": {"type": "number", "minimum": 0.2, "maximum": 1.2, "default": 0.7},
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
        config.update(FROZEN_ROUND3_CONFIG)
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


def _apply_red_inter_team_buffer(env: Any, actions: dict[int, np.ndarray], config: dict[str, Any]) -> dict[int, np.ndarray]:
    """Frozen Round-3 red avoidance buffer."""
    adjusted = dict(actions)
    risk_margin = float(config["red_risk_margin"])
    separation_gain = float(config["shared_separation_gain"])
    threshold = float(getattr(env.cfg.drone, "inter_team_safe_dist", 0.8)) + risk_margin + 0.8
    for drone in env.drones:
        if _team_name(drone) != "red":
            continue
        avoidance = np.zeros(3, dtype=np.float32)
        for other in env.drones:
            if _team_name(other) == "red":
                continue
            delta = np.asarray(drone.position - other.position, dtype=np.float32)
            distance = float(np.linalg.norm(delta))
            if distance < 1e-6 or distance >= threshold:
                continue
            avoidance += _unit(delta) * separation_gain * (threshold - distance) / threshold
        if np.linalg.norm(avoidance) < 1e-6:
            continue
        current = np.asarray(adjusted.get(drone.id, np.zeros(3, dtype=np.float32)), dtype=np.float32)
        max_accel = float(getattr(drone.dynamics, "max_accel", 10.0))
        adjusted[drone.id] = _limit_norm(current + avoidance, max_accel).astype(np.float32)
    return adjusted


def _apply_blue_intercept_pressure(env: Any, actions: dict[int, np.ndarray], config: dict[str, Any]) -> dict[int, np.ndarray]:
    adjusted = dict(actions)
    red_racers = [drone for drone in env.drones if _team_name(drone) == "red" and _role_name(drone) == "racer"]
    if not red_racers:
        return adjusted

    gain = float(config["blue_intercept_gain"])
    radius = float(config["blue_intercept_radius"])
    buffer = float(config["blue_pressure_buffer"])
    safe_dist = float(getattr(env.cfg.drone, "inter_team_safe_dist", 0.8)) + buffer
    for drone in env.drones:
        if _team_name(drone) != "blue":
            continue

        current = np.asarray(adjusted.get(drone.id, np.zeros(3, dtype=np.float32)), dtype=np.float32)
        max_accel = float(getattr(drone.dynamics, "max_accel", 10.0))
        if _role_name(drone) == "defender":
            target = max(
                red_racers,
                key=lambda other: (
                    int(getattr(other, "gate_pass_count", 0)),
                    -float(np.linalg.norm(np.asarray(other.position - drone.position, dtype=np.float32))),
                ),
            )
            delta = np.asarray(target.position - drone.position, dtype=np.float32)
            distance = float(np.linalg.norm(delta))
            if distance <= radius:
                lead_dir = _unit(np.asarray(target.velocity, dtype=np.float32))
                if np.linalg.norm(lead_dir) < 1e-6:
                    lead_dir = np.array([1.0, 0.0, 0.0], dtype=np.float32)
                standoff = np.asarray(target.position, dtype=np.float32) + lead_dir * (safe_dist + 0.9)
                standoff += np.array([0.0, 0.0, 0.8], dtype=np.float32)
                z_range = getattr(env.cfg.field, "z_range", (0.0, 10.0))
                standoff[2] = float(np.clip(standoff[2], z_range[0] + 1.0, z_range[1] - 1.0))
                pressure = _unit(standoff - drone.position) * gain
                if distance < safe_dist + 0.5:
                    pressure += _unit(np.asarray(drone.position - target.position, dtype=np.float32)) * gain
                adjusted[drone.id] = _limit_norm(current + pressure, max_accel).astype(np.float32)
            continue

        avoidance = np.zeros(3, dtype=np.float32)
        for target in red_racers:
            delta = np.asarray(drone.position - target.position, dtype=np.float32)
            distance = float(np.linalg.norm(delta))
            if distance < 1e-6 or distance >= safe_dist:
                continue
            avoidance += _unit(delta) * gain * (safe_dist - distance) / safe_dist
        if np.linalg.norm(avoidance) >= 1e-6:
            adjusted[drone.id] = _limit_norm(current + avoidance, max_accel).astype(np.float32)
    return adjusted


def _apply_blue_racer_gate_drive(
    env: Any,
    actions: dict[int, np.ndarray],
    config: dict[str, Any],
    controller: SafeRulePolicy,
) -> dict[int, np.ndarray]:
    adjusted = dict(actions)
    if not getattr(env, "gates", None):
        return adjusted

    blue_racers = [drone for drone in env.drones if _team_name(drone) == "blue" and _role_name(drone) == "racer"]
    blue_racers.sort(key=lambda drone: drone.id)
    if not blue_racers:
        return adjusted

    drive_gain = min(float(config["blue_intercept_gain"]) * 0.35, 1.15)
    pressure_buffer = float(config["blue_pressure_buffer"])
    close_red_threshold = float(getattr(env.cfg.drone, "inter_team_safe_dist", 0.8)) + pressure_buffer + 1.0
    close_any_threshold = float(getattr(env.cfg.drone, "intra_team_safe_dist", 0.6)) + float(config["blue_risk_margin"]) + 0.4
    desired_speed = float(config["blue_desired_speed"])

    for drone in blue_racers:
        current = np.asarray(adjusted.get(drone.id, np.zeros(3, dtype=np.float32)), dtype=np.float32)
        if _has_close_drone(env, drone, close_red_threshold, close_any_threshold):
            continue
        if float(np.linalg.norm(drone.velocity)) > 0.25 and float(np.dot(current, drone.velocity)) < 0.0:
            continue

        gate_index = int(controller.gate_indices.get(drone.id, len(env.gates) - 1)) % len(env.gates)
        gate = env.gates[gate_index]
        crossing_dir = -np.asarray(gate.normal, dtype=np.float32)
        lane = _blue_lane_offset(env, blue_racers, drone, gate, float(config["blue_lane_spacing"]))
        signed_dist = float(np.dot(np.asarray(drone.position - gate.center, dtype=np.float32), crossing_dir))
        if signed_dist > -0.25:
            target = gate.center + lane - crossing_dir * float(config["shared_gate_approach_offset"])
        else:
            target = gate.center + lane + crossing_dir * float(config["shared_gate_exit_offset"])

        target_velocity = _unit(np.asarray(target - drone.position, dtype=np.float32)) * min(
            desired_speed + 0.2,
            float(getattr(drone.dynamics, "max_speed", desired_speed)),
        )
        drive = (target_velocity - np.asarray(drone.velocity, dtype=np.float32)) * drive_gain
        max_accel = float(getattr(drone.dynamics, "max_accel", 10.0))
        adjusted[drone.id] = _limit_norm(current + drive, max_accel).astype(np.float32)

    return adjusted


def _apply_blue_defender_gate_frame_guard(
    env: Any,
    actions: dict[int, np.ndarray],
    config: dict[str, Any],
) -> dict[int, np.ndarray]:
    adjusted = dict(actions)
    if not getattr(env, "gates", None):
        return adjusted

    radius = float(getattr(env.cfg.drone, "safety_radius", 0.5))
    frame_margin = radius + 0.12
    aperture_padding = radius + 0.18
    guard_gain = max(float(config["blue_intercept_gain"]), 2.5)
    dt = float(getattr(env.cfg, "dt", 0.05))

    for drone in env.drones:
        if _team_name(drone) != "blue" or _role_name(drone) != "defender":
            continue

        current = np.asarray(adjusted.get(drone.id, np.zeros(3, dtype=np.float32)), dtype=np.float32)
        next_state = drone.dynamics.step(drone.state.copy(), current, dt)
        next_pos = drone.dynamics.get_position(next_state)
        correction = np.zeros(3, dtype=np.float32)

        for gate in env.gates:
            escape = _gate_frame_escape(next_pos, gate, radius, frame_margin, aperture_padding)
            if np.linalg.norm(escape) >= 1e-6:
                correction += escape

        if np.linalg.norm(correction) < 1e-6:
            continue

        max_accel = float(getattr(drone.dynamics, "max_accel", 10.0))
        adjusted[drone.id] = _limit_norm(current + _unit(correction) * guard_gain, max_accel).astype(np.float32)

    return adjusted


def _gate_frame_escape(
    position: np.ndarray,
    gate: Any,
    radius: float,
    frame_margin: float,
    aperture_padding: float,
) -> np.ndarray:
    local = np.asarray(position - gate.center, dtype=np.float32)
    normal = np.asarray(gate.normal, dtype=np.float32)
    tangent_h = np.asarray(gate.tangent_h, dtype=np.float32)
    tangent_v = np.asarray(gate.tangent_v, dtype=np.float32)
    plane_dist = float(np.dot(local, normal))
    if abs(plane_dist) > frame_margin:
        return np.zeros(3, dtype=np.float32)

    u = float(np.dot(local, tangent_h))
    v = float(np.dot(local, tangent_v))
    safe_u = max(float(gate.width) / 2.0 - aperture_padding, 0.0)
    safe_v = max(float(gate.height) / 2.0 - aperture_padding, 0.0)
    outside_safe_aperture = abs(u) > safe_u or abs(v) > safe_v
    if not outside_safe_aperture:
        return np.zeros(3, dtype=np.float32)

    target_on_plane = np.asarray(gate.center, dtype=np.float32)
    target_on_plane += tangent_h * float(np.clip(u, -safe_u, safe_u))
    target_on_plane += tangent_v * float(np.clip(v, -safe_v, safe_v))
    escape = target_on_plane - np.asarray(position, dtype=np.float32)
    if abs(plane_dist) < radius + 0.05:
        sign = 1.0 if plane_dist >= 0.0 else -1.0
        escape += normal * sign * (radius + 0.2 - abs(plane_dist))
    return escape.astype(np.float32)


def _blue_lane_offset(env: Any, racers: list[Any], drone: Any, gate: Any, lane_spacing: float) -> np.ndarray:
    if len(racers) <= 1 or drone not in racers:
        return np.zeros(3, dtype=np.float32)
    centered_idx = racers.index(drone) - (len(racers) - 1) / 2
    max_offset = max(float(gate.width) / 2 - float(env.cfg.drone.safety_radius) - 0.05, 0.0)
    offset = float(np.clip(centered_idx * lane_spacing, -max_offset, max_offset))
    return (np.asarray(gate.tangent_h, dtype=np.float32) * offset).astype(np.float32)


def _has_close_drone(env: Any, drone: Any, red_threshold: float, other_threshold: float) -> bool:
    for other in env.drones:
        if getattr(other, "id", None) == getattr(drone, "id", None):
            continue
        distance = float(np.linalg.norm(np.asarray(drone.position - other.position, dtype=np.float32)))
        if _team_name(other) == "red" and distance < red_threshold:
            return True
        if distance < other_threshold:
            return True
    return False


def _team_name(drone: Any) -> str:
    return str(getattr(getattr(drone, "team", None), "name", "")).lower()


def _role_name(drone: Any) -> str:
    return str(getattr(getattr(drone, "role", None), "name", "")).lower()


def _limit_norm(vector: np.ndarray, max_norm: float) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm <= max_norm or norm < 1e-6:
        return vector
    return vector / norm * max_norm


def _unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        return np.zeros(3, dtype=np.float32)
    return vector / norm
