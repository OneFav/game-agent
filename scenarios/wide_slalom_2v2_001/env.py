from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass
class AgentState:
    position: np.ndarray
    velocity: np.ndarray


class Box:
    def __init__(self, low: np.ndarray, high: np.ndarray, shape: tuple[int, ...], dtype: Any = np.float32) -> None:
        self.low = low.astype(dtype)
        self.high = high.astype(dtype)
        self.shape = shape
        self.dtype = dtype

    def sample(self) -> np.ndarray:
        return np.zeros(self.shape, dtype=self.dtype)


class DroneRingEnv:
    metadata = {"render_modes": ["human", "rgb_array"], "name": "wide_slalom_2v2_001_v0"}

    observation_shape = (32,)
    action_shape = (4,)
    agents = ["red_racer_0", "red_defender_0", "blue_racer_0", "blue_defender_0"]
    possible_agents = agents[:]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.max_steps = int(config.get("max_steps", 600))
        self.dt = float(config.get("dt", 0.1))
        self.boundary = float((config.get("field") or {}).get("boundary", config.get("boundary", 25.0)))
        self.ring_radius = float(config.get("ring_radius", 1.5))
        self.collision_radius = float(config.get("collision_radius", 0.5))
        self.interception_radius = float(config.get("interception_radius", 0.8))
        self.max_speed = float(config.get("max_speed", 8.0))
        self.communication_mode = (config.get("communication") or {}).get("mode", "perfect")
        self._action_low = np.asarray(config.get("action_low", [-1.0, -1.0, -1.0, -1.0]), dtype=np.float32)
        self._action_high = np.asarray(config.get("action_high", [1.0, 1.0, 1.0, 1.0]), dtype=np.float32)
        self._gates = [np.asarray(gate, dtype=np.float32) for gate in config.get("gates", _default_gates())]
        self._initial_positions = {
            agent_id: np.asarray(position, dtype=np.float32)
            for agent_id, position in (config.get("initial_positions") or _default_positions()).items()
        }
        self._states: dict[str, AgentState] = {}
        self._step_count = 0
        self._next_gate = 0
        self._last_action_clipped = {agent_id: False for agent_id in self.agents}
        self._rng = np.random.default_rng(0)
        self._obs_space = Box(
            low=np.array(
                [-25.0, -25.0, -8.0, -8.0]
                + [-50.0, -50.0, -8.0, -8.0]
                + [-50.0, -50.0, -8.0, -8.0]
                + [-50.0, -50.0, -8.0, -8.0]
                + [0.0, -1.0, -1.0, 0.0]
                + [0.0, 0.0, 0.0, 0.0]
                + [-50.0, -50.0, -8.0, -8.0]
                + [0.0, 0.0],
                dtype=np.float32,
            ),
            high=np.array(
                [25.0, 25.0, 8.0, 8.0]
                + [50.0, 50.0, 8.0, 8.0]
                + [50.0, 50.0, 8.0, 8.0]
                + [50.0, 50.0, 8.0, 8.0]
                + [1.0, 1.0, 1.0, 80.0]
                + [1.0, 1.0, 1.0, 1.0]
                + [50.0, 50.0, 8.0, 8.0]
                + [float(len(self._gates)), 1.0],
                dtype=np.float32,
            ),
            shape=self.observation_shape,
        )
        self._act_space = Box(low=self._action_low, high=self._action_high, shape=self.action_shape)

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None):
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._next_gate = 0
        self._last_action_clipped = {agent_id: False for agent_id in self.agents}
        self._states = {
            agent_id: AgentState(position.copy(), np.zeros(2, dtype=np.float32))
            for agent_id, position in self._initial_positions.items()
        }
        infos = {agent_id: self._info(agent_id, collision=False, out_of_bounds=False) for agent_id in self.agents}
        return self._observations(), infos

    def step(self, actions: dict[str, np.ndarray]):
        self._step_count += 1
        for agent_id in self.agents:
            action = np.asarray(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)), dtype=np.float32)
            if action.shape != self.action_shape:
                raise ValueError(f"Action shape for {agent_id} must be {self.action_shape}, got {action.shape}")
            clipped = np.clip(action, self._action_low, self._action_high)
            self._last_action_clipped[agent_id] = bool(np.any(clipped != action))
            velocity = clipped[:2] * self.max_speed
            self._states[agent_id].velocity = velocity.astype(np.float32)
            self._states[agent_id].position = (self._states[agent_id].position + velocity * self.dt).astype(np.float32)

        gate_passed = self._update_gate_progress()
        collision = self._has_collision()
        interception = self._distance("red_racer_0", "blue_defender_0") <= self.interception_radius
        out_of_bounds = self._out_of_bounds()
        success = self._next_gate >= len(self._gates)
        terminated_any = success or collision or interception or out_of_bounds
        truncated_any = self._step_count >= self.max_steps and not terminated_any

        rewards = self._rewards(gate_passed, success, collision, interception, out_of_bounds)
        terminations = {agent_id: terminated_any for agent_id in self.agents}
        truncations = {agent_id: truncated_any for agent_id in self.agents}
        infos = {agent_id: self._info(agent_id, collision=collision or interception, out_of_bounds=out_of_bounds) for agent_id in self.agents}
        return self._observations(), rewards, terminations, truncations, infos

    def observation_space(self, agent: str) -> Box:
        return self._obs_space

    def action_space(self, agent: str) -> Box:
        return self._act_space

    def render(self):
        return None

    def close(self) -> None:
        return None

    def _observations(self) -> dict[str, np.ndarray]:
        return {agent_id: self._observation(agent_id) for agent_id in self.agents}

    def _observation(self, agent_id: str) -> np.ndarray:
        own = self._states[agent_id]
        teammate_id = self._teammate(agent_id)
        teammate = self._states[teammate_id]
        opponent_ids = self._opponents(agent_id)
        first_opponent = self._states[opponent_ids[0]]
        second_opponent = self._states[opponent_ids[1]]
        gate_vector = self._target_gate() - own.position
        gate_distance = float(np.linalg.norm(gate_vector))
        gate_direction = gate_vector / max(gate_distance, 1e-6)

        obs = np.zeros(self.observation_shape, dtype=np.float32)
        obs[0:2] = own.position
        obs[2:4] = own.velocity
        obs[4:6] = teammate.position - own.position
        obs[6:8] = teammate.velocity - own.velocity
        obs[8:10] = first_opponent.position - own.position
        obs[10:12] = first_opponent.velocity - own.velocity
        obs[12:14] = second_opponent.position - own.position
        obs[14:16] = second_opponent.velocity - own.velocity
        obs[16] = (len(self._gates) - self._next_gate) / max(len(self._gates), 1)
        obs[17:19] = gate_direction.astype(np.float32)
        obs[19] = gate_distance
        obs[20:24] = _role_one_hot(agent_id)
        obs[24:26] = gate_vector.astype(np.float32)
        nearest = min(opponent_ids, key=lambda candidate: self._distance(agent_id, candidate))
        obs[26:28] = self._states[nearest].position - own.position
        obs[28:30] = self._states[nearest].velocity - own.velocity
        obs[30] = float(self._next_gate)
        obs[31] = float(self._step_count) / max(float(self.max_steps), 1.0)
        return obs

    def _opponents(self, agent_id: str) -> list[str]:
        own_team = agent_id.split("_", 1)[0]
        return [candidate for candidate in self.agents if not candidate.startswith(own_team)]

    def _teammate(self, agent_id: str) -> str:
        own_team = agent_id.split("_", 1)[0]
        teammates = [candidate for candidate in self.agents if candidate != agent_id and candidate.startswith(own_team)]
        return teammates[0]

    def _target_gate(self) -> np.ndarray:
        if self._next_gate >= len(self._gates):
            return self._gates[-1]
        return self._gates[self._next_gate]

    def _update_gate_progress(self) -> bool:
        if self._next_gate >= len(self._gates):
            return False
        if self._distance_to_point("red_racer_0", self._gates[self._next_gate]) <= self.ring_radius:
            self._next_gate += 1
            return True
        return False

    def _has_collision(self) -> bool:
        for index, first in enumerate(self.agents):
            for second in self.agents[index + 1:]:
                if self._distance(first, second) <= self.collision_radius:
                    return True
        return False

    def _out_of_bounds(self) -> bool:
        return any(np.any(np.abs(state.position) > self.boundary) for state in self._states.values())

    def _rewards(self, gate_passed: bool, success: bool, collision: bool, interception: bool, out_of_bounds: bool) -> dict[str, float]:
        rewards = {agent_id: -0.01 for agent_id in self.agents}
        if gate_passed:
            rewards["red_racer_0"] += 1.0
        if success:
            rewards["red_racer_0"] += 5.0
            rewards["red_defender_0"] += 1.0
        escort_error = abs(self._distance("red_racer_0", "red_defender_0") - 2.0)
        rewards["red_defender_0"] += max(0.0, 0.2 - 0.05 * escort_error)
        rewards["blue_defender_0"] += max(0.0, 0.5 - 0.05 * self._distance("red_racer_0", "blue_defender_0"))
        if interception:
            rewards["blue_defender_0"] += 2.0
            rewards["red_racer_0"] -= 2.0
        if collision or out_of_bounds:
            for agent_id in self.agents:
                rewards[agent_id] -= 5.0
        return {agent_id: float(value) for agent_id, value in rewards.items()}

    def _info(self, agent_id: str, collision: bool, out_of_bounds: bool) -> dict[str, Any]:
        return {
            "collision": bool(collision),
            "out_of_bounds": bool(out_of_bounds),
            "ring_passed_count": int(self._next_gate),
            "communication_dropped": False,
            "action_clipped": bool(self._last_action_clipped.get(agent_id, False)),
            "gate_passed_count": int(self._next_gate),
            "role": _role(agent_id),
            "team": agent_id.split("_", 1)[0],
        }

    def _distance(self, first: str, second: str) -> float:
        return self._distance_to_point(first, self._states[second].position)

    def _distance_to_point(self, agent_id: str, point: np.ndarray) -> float:
        return float(np.linalg.norm(self._states[agent_id].position - point))


def _default_gates() -> list[list[float]]:
    return [[-15.0, -6.0], [-9.0, 5.0], [-3.0, -5.0], [3.0, 5.0], [9.0, -5.0], [15.0, 6.0]]


def _default_positions() -> dict[str, list[float]]:
    return {
        "red_racer_0": [-21.0, -2.0],
        "red_defender_0": [-22.0, -4.0],
        "blue_racer_0": [21.0, 2.0],
        "blue_defender_0": [20.0, 4.0],
    }


def _role(agent_id: str) -> str:
    if "racer" in agent_id:
        return "racer"
    return "defender"


def _role_one_hot(agent_id: str) -> np.ndarray:
    return np.array(
        [
            1.0 if agent_id.startswith("red") else 0.0,
            1.0 if agent_id.startswith("blue") else 0.0,
            1.0 if "racer" in agent_id else 0.0,
            1.0 if "defender" in agent_id else 0.0,
        ],
        dtype=np.float32,
    )


def make_env(config: dict[str, Any] | None = None) -> DroneRingEnv:
    config_path = Path(__file__).with_name("env_config.yaml")
    base = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if config:
        base.update(config)
    return DroneRingEnv(base)
