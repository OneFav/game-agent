from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class AgentState:
    position: np.ndarray
    velocity: np.ndarray


class DroneRingEnv:
    """Lightweight two-agent drone ring environment with a parallel-style API."""

    observation_shape = (12,)
    action_shape = (4,)
    agents = ["red_0", "blue_0"]

    _ACTION_LOW = np.array([-2.0, -2.0, -1.0, -1.0], dtype=np.float32)
    _ACTION_HIGH = np.array([2.0, 2.0, 1.0, 1.0], dtype=np.float32)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.ring_count = int(config.get("ring_count", 3))
        self.max_steps = int(config.get("max_steps", 200))
        self.dt = float(config.get("dt", 0.1))
        self.ring_radius = float(config.get("ring_radius", 0.45))
        self.collision_radius = float(config.get("collision_radius", 0.25))
        self.boundary = float(config.get("boundary", 10.0))

        self.rings = [np.array([2.5 + i * 2.0, 0.0], dtype=np.float32) for i in range(self.ring_count)]
        self._states: dict[str, AgentState] = {}
        self._step_count = 0
        self._next_ring = 0
        self._rng = np.random.default_rng()

    def reset(self, seed: int | None = None) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._next_ring = 0

        jitter = self._rng.normal(0.0, 0.01, size=(2, 2)).astype(np.float32)
        self._states = {
            "red_0": AgentState(np.array([0.0, -0.5], dtype=np.float32) + jitter[0], np.zeros(2, dtype=np.float32)),
            "blue_0": AgentState(np.array([0.0, 0.5], dtype=np.float32) + jitter[1], np.zeros(2, dtype=np.float32)),
        }
        return self._observations(), {"seed": seed, "metrics": self._metrics(False, False, False)}

    def step(
        self, actions: dict[str, np.ndarray]
    ) -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, bool], dict[str, bool], dict[str, Any]]:
        self._step_count += 1

        for agent_id in self.agents:
            action = self._clip_action(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)))
            state = self._states[agent_id]
            acceleration = action[:2]
            state.velocity = (state.velocity + acceleration * self.dt).astype(np.float32)
            state.position = (state.position + state.velocity * self.dt).astype(np.float32)

        passed_ring = self._update_ring_progress()
        red_success = self._next_ring >= self.ring_count
        blue_collision = self._distance("red_0", "blue_0") <= self.collision_radius
        out_of_bounds = any(np.any(np.abs(self._states[agent_id].position) > self.boundary) for agent_id in self.agents)
        timeout_reached = self._step_count >= self.max_steps
        terminated_any = red_success or blue_collision or out_of_bounds
        truncated_any = timeout_reached and not terminated_any

        rewards = self._rewards(passed_ring, red_success, blue_collision, out_of_bounds, truncated_any)
        terminated = {agent_id: terminated_any for agent_id in self.agents}
        truncated = {agent_id: truncated_any for agent_id in self.agents}
        info = {"metrics": self._metrics(red_success, blue_collision, out_of_bounds, truncated_any)}
        return self._observations(), rewards, terminated, truncated, info

    def _clip_action(self, action: np.ndarray) -> np.ndarray:
        action_array = np.asarray(action, dtype=np.float32)
        if action_array.shape != self.action_shape:
            raise ValueError(f"Action shape must be {self.action_shape}, got {action_array.shape}")
        return np.clip(action_array, self._ACTION_LOW, self._ACTION_HIGH)

    def _update_ring_progress(self) -> bool:
        if self._next_ring >= self.ring_count:
            return False
        ring = self.rings[self._next_ring]
        if np.linalg.norm(self._states["red_0"].position - ring) <= self.ring_radius:
            self._next_ring += 1
            return True
        return False

    def _rewards(
        self,
        passed_ring: bool,
        red_success: bool,
        blue_collision: bool,
        out_of_bounds: bool,
        timeout: bool,
    ) -> dict[str, float]:
        red_reward = -0.01 + (1.0 if passed_ring else 0.0) + (5.0 if red_success else 0.0)
        blue_reward = -0.01 + (2.0 if blue_collision else 0.0)
        if out_of_bounds:
            red_reward -= 1.0
            blue_reward -= 1.0
        if timeout:
            red_reward -= 0.5
            blue_reward += 0.5
        return {"red_0": float(red_reward), "blue_0": float(blue_reward)}

    def _metrics(
        self,
        red_success: bool,
        blue_collision: bool,
        out_of_bounds: bool,
        timeout: bool = False,
    ) -> dict[str, Any]:
        return {
            "red_rings_passed": self._next_ring,
            "success": red_success,
            "collision": blue_collision,
            "out_of_bounds": out_of_bounds,
            "timeout": timeout,
            "episode_length": self._step_count,
        }

    def _observations(self) -> dict[str, np.ndarray]:
        return {agent_id: self._observation(agent_id) for agent_id in self.agents}

    def _observation(self, agent_id: str) -> np.ndarray:
        own = self._states[agent_id]
        opponent_id = "blue_0" if agent_id == "red_0" else "red_0"
        opponent = self._states[opponent_id]
        ring_vector = self._target_ring() - own.position
        ring_distance = float(np.linalg.norm(ring_vector))
        ring_direction = ring_vector / max(ring_distance, 1e-6)

        obs = np.zeros(self.observation_shape, dtype=np.float32)
        obs[0:2] = own.position
        obs[2:4] = own.velocity
        obs[4:6] = opponent.position - own.position
        obs[6:8] = opponent.velocity - own.velocity
        obs[8] = (self.ring_count - self._next_ring) / max(self.ring_count, 1)
        obs[9:11] = ring_direction.astype(np.float32)
        obs[11] = ring_distance
        return obs

    def _target_ring(self) -> np.ndarray:
        if self._next_ring >= self.ring_count:
            return self.rings[-1] if self.rings else np.zeros(2, dtype=np.float32)
        return self.rings[self._next_ring]

    def _distance(self, first: str, second: str) -> float:
        return float(np.linalg.norm(self._states[first].position - self._states[second].position))
