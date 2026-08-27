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


class DroneRingLossyEnv:
    observation_shape = (12,)
    action_shape = (4,)
    agents = ["red_0", "blue_0"]

    _ACTION_LOW = np.array([-2.0, -2.0, -1.0, -1.0], dtype=np.float32)
    _ACTION_HIGH = np.array([2.0, 2.0, 1.0, 1.0], dtype=np.float32)
    _RING_Y_PATTERN = (0.0, 0.75, -0.75, 0.45, -0.45)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = dict(config or {})
        self.ring_count = int(config.get("ring_count", 3))
        self.max_steps = int(config.get("max_steps", 200))
        self.dt = float(config.get("dt", 0.18))
        self.ring_radius = float(config.get("ring_radius", 0.55))
        self.collision_radius = float(config.get("collision_radius", 0.28))
        self.boundary = float(config.get("boundary", 9.0))
        self.drop_probability = float(config.get("drop_probability", 0.1))
        self.blue_spawn_offset = float(config.get("blue_spawn_offset", 1.0))
        self.red_spawn_y = float(config.get("red_spawn_y", -0.55))
        self.blue_chase_boost = float(config.get("blue_chase_boost", 0.05))

        self.rings = [
            np.array([2.3 + index * 2.05, self._RING_Y_PATTERN[index % len(self._RING_Y_PATTERN)]], dtype=np.float32)
            for index in range(self.ring_count)
        ]
        self._rng = np.random.default_rng()
        self._states: dict[str, AgentState] = {}
        self._step_count = 0
        self._next_ring = 0
        self._last_packet_flags: dict[str, dict[str, bool]] = {}
        self._last_action_clipped: dict[str, bool] = {agent_id: False for agent_id in self.agents}
        self._last_communication_drop_count = 0

    def reset(self, seed: int | None = None) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._next_ring = 0

        jitter = self._rng.normal(0.0, 0.015, size=(2, 2)).astype(np.float32)
        self._states = {
            "red_0": AgentState(
                position=np.array([-0.2, self.red_spawn_y], dtype=np.float32) + jitter[0],
                velocity=np.zeros(2, dtype=np.float32),
            ),
            "blue_0": AgentState(
                position=np.array([0.1, self.blue_spawn_offset], dtype=np.float32) + jitter[1],
                velocity=np.array([self.blue_chase_boost, 0.0], dtype=np.float32),
            ),
        }
        self._last_action_clipped = {agent_id: False for agent_id in self.agents}
        observations = self._observations()
        return observations, self._info(red_success=False, collision=False, out_of_bounds=False, timeout=False, passed_ring=False)

    def step(
        self, actions: dict[str, np.ndarray]
    ) -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, bool], dict[str, bool], dict[str, Any]]:
        self._step_count += 1

        clipped_actions: dict[str, np.ndarray] = {}
        for agent_id in self.agents:
            clipped_actions[agent_id] = self._clip_action(agent_id, actions.get(agent_id))

        for agent_id, action in clipped_actions.items():
            state = self._states[agent_id]
            acceleration = action[:2]
            state.velocity = (state.velocity + acceleration * self.dt).astype(np.float32)
            speed_limit = 1.55 if agent_id.startswith("red") else 1.35
            speed = float(np.linalg.norm(state.velocity))
            if speed > speed_limit:
                state.velocity = (state.velocity / speed * speed_limit).astype(np.float32)
            state.position = (state.position + state.velocity * self.dt).astype(np.float32)

        passed_ring = self._update_ring_progress()
        red_success = self._next_ring >= self.ring_count
        collision = self._distance("red_0", "blue_0") <= self.collision_radius
        out_of_bounds = any(np.any(np.abs(self._states[agent_id].position) > self.boundary) for agent_id in self.agents)
        timeout = self._step_count >= self.max_steps and not (red_success or collision or out_of_bounds)

        terminated_any = red_success or collision or out_of_bounds
        truncated_any = timeout
        observations = self._observations()
        rewards = self._rewards(passed_ring, red_success, collision, out_of_bounds, timeout)
        terminated = {agent_id: terminated_any for agent_id in self.agents}
        truncated = {agent_id: truncated_any for agent_id in self.agents}
        info = self._info(
            red_success=red_success,
            collision=collision,
            out_of_bounds=out_of_bounds,
            timeout=timeout,
            passed_ring=passed_ring,
        )
        return observations, rewards, terminated, truncated, info

    def render(self) -> dict[str, Any]:
        return {
            "step_count": self._step_count,
            "next_ring": self._next_ring,
            "rings": [ring.copy() for ring in self.rings],
            "states": {
                agent_id: {
                    "position": state.position.copy(),
                    "velocity": state.velocity.copy(),
                }
                for agent_id, state in self._states.items()
            },
        }

    def close(self) -> None:
        return None

    def _clip_action(self, agent_id: str, action: Any) -> np.ndarray:
        action_array = np.asarray(
            np.zeros(self.action_shape, dtype=np.float32) if action is None else action,
            dtype=np.float32,
        )
        if action_array.shape != self.action_shape:
            raise ValueError(f"Action shape must be {self.action_shape}, got {action_array.shape}")
        clipped = np.clip(action_array, self._ACTION_LOW, self._ACTION_HIGH).astype(np.float32)
        self._last_action_clipped[agent_id] = bool(np.any(np.abs(clipped - action_array) > 1e-6))
        return clipped

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
        collision: bool,
        out_of_bounds: bool,
        timeout: bool,
    ) -> dict[str, float]:
        red_reward = -0.01 + (1.25 if passed_ring else 0.0) + (4.0 if red_success else 0.0)
        blue_reward = -0.01 + (1.8 if collision else 0.0)
        if out_of_bounds:
            red_reward -= 1.0
            blue_reward -= 0.6
        if timeout:
            red_reward -= 0.5
            blue_reward += 0.2
        return {"red_0": float(red_reward), "blue_0": float(blue_reward)}

    def _info(
        self,
        red_success: bool,
        collision: bool,
        out_of_bounds: bool,
        timeout: bool,
        passed_ring: bool,
    ) -> dict[str, Any]:
        return {
            "collision": collision,
            "out_of_bounds": out_of_bounds,
            "ring_passed_count": self._next_ring,
            "communication_dropped": {
                "per_agent": self._last_packet_flags,
                "drop_events": self._last_communication_drop_count,
            },
            "action_clipped": dict(self._last_action_clipped),
            "metrics": {
                "red_rings_passed": self._next_ring,
                "ring_passed_count": self._next_ring,
                "success": red_success,
                "collision": collision,
                "out_of_bounds": out_of_bounds,
                "timeout": timeout,
                "episode_length": self._step_count,
                "communication_drop_events": self._last_communication_drop_count,
                "passed_ring_this_step": passed_ring,
            },
        }

    def _observations(self) -> dict[str, np.ndarray]:
        observations = {agent_id: self._observation(agent_id) for agent_id in self.agents}
        self._last_communication_drop_count = sum(
            int(flags["opponent"]) + int(flags["target"]) for flags in self._last_packet_flags.values()
        )
        return observations

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

        opponent_dropped = bool(self._rng.random() < self.drop_probability)
        target_dropped = bool(self._rng.random() < self.drop_probability)
        if opponent_dropped:
            obs[4:8] = 0.0
        if target_dropped:
            obs[9:12] = 0.0

        self._last_packet_flags[agent_id] = {"opponent": opponent_dropped, "target": target_dropped}
        return obs

    def _target_ring(self) -> np.ndarray:
        if self._next_ring >= self.ring_count:
            return self.rings[-1]
        return self.rings[self._next_ring]

    def _distance(self, first: str, second: str) -> float:
        return float(np.linalg.norm(self._states[first].position - self._states[second].position))


def make_env(config: dict[str, Any] | None = None) -> DroneRingLossyEnv:
    config_path = Path(__file__).with_name("env_config.yaml")
    base = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base.update(config or {})
    return DroneRingLossyEnv(base)
