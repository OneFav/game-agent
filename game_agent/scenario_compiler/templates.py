from __future__ import annotations

SCENARIO_ENV_PY = """import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def _ensure_project_root_on_path():
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "game_agent").is_dir():
            sys.path.insert(0, str(candidate))
            return


_ensure_project_root_on_path()

try:
    from game_agent.envs.drone_ring_game.env import DroneRingEnv
except ModuleNotFoundError:
    @dataclass
    class AgentState:
        position: np.ndarray
        velocity: np.ndarray


    class DroneRingEnv:
        observation_shape = (12,)
        action_shape = (4,)
        agents = ["red_0", "blue_0"]

        _ACTION_LOW = np.array([-2.0, -2.0, -1.0, -1.0], dtype=np.float32)
        _ACTION_HIGH = np.array([2.0, 2.0, 1.0, 1.0], dtype=np.float32)

        def __init__(self, config: dict[str, Any] | None = None) -> None:
            config = config or {}
            self.ring_count = int(config.get("ring_count", 2))
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

        def reset(self, seed: int | None = None):
            self._rng = np.random.default_rng(seed)
            self._step_count = 0
            self._next_ring = 0
            jitter = self._rng.normal(0.0, 0.01, size=(2, 2)).astype(np.float32)
            self._states = {
                "red_0": AgentState(np.array([0.0, -0.5], dtype=np.float32) + jitter[0], np.zeros(2, dtype=np.float32)),
                "blue_0": AgentState(np.array([0.0, 0.5], dtype=np.float32) + jitter[1], np.zeros(2, dtype=np.float32)),
            }
            return self._observations(), {"seed": seed, "metrics": self._metrics(False, False, False)}

        def step(self, actions):
            self._step_count += 1
            for agent_id in self.agents:
                action = np.asarray(actions.get(agent_id, np.zeros(self.action_shape, dtype=np.float32)), dtype=np.float32)
                if action.shape != self.action_shape:
                    raise ValueError(f"Action shape must be {self.action_shape}, got {action.shape}")
                action = np.clip(action, self._ACTION_LOW, self._ACTION_HIGH)
                state = self._states[agent_id]
                state.velocity = (state.velocity + action[:2] * self.dt).astype(np.float32)
                state.position = (state.position + state.velocity * self.dt).astype(np.float32)

            red_success = self._next_ring >= self.ring_count
            blue_collision = self._distance("red_0", "blue_0") <= self.collision_radius
            out_of_bounds = any(np.any(np.abs(self._states[agent_id].position) > self.boundary) for agent_id in self.agents)
            timeout = self._step_count >= self.max_steps and not (red_success or blue_collision or out_of_bounds)
            terminated_any = red_success or blue_collision or out_of_bounds
            rewards = {"red_0": -0.01, "blue_0": -0.01}
            terminated = {agent_id: terminated_any for agent_id in self.agents}
            truncated = {agent_id: timeout for agent_id in self.agents}
            return self._observations(), rewards, terminated, truncated, {"metrics": self._metrics(red_success, blue_collision, out_of_bounds, timeout)}

        def _metrics(self, red_success: bool, blue_collision: bool, out_of_bounds: bool, timeout: bool = False):
            return {
                "red_rings_passed": self._next_ring,
                "success": red_success,
                "collision": blue_collision,
                "out_of_bounds": out_of_bounds,
                "timeout": timeout,
                "episode_length": self._step_count,
            }

        def _observations(self):
            return {agent_id: self._observation(agent_id) for agent_id in self.agents}

        def _observation(self, agent_id: str):
            own = self._states[agent_id]
            opponent_id = "blue_0" if agent_id == "red_0" else "red_0"
            opponent = self._states[opponent_id]
            obs = np.zeros(self.observation_shape, dtype=np.float32)
            obs[0:2] = own.position
            obs[2:4] = own.velocity
            obs[4:6] = opponent.position - own.position
            obs[6:8] = opponent.velocity - own.velocity
            obs[8] = 1.0
            obs[9:11] = np.array([1.0, 0.0], dtype=np.float32)
            obs[11] = 0.0
            return obs

        def _distance(self, first: str, second: str) -> float:
            return float(np.linalg.norm(self._states[first].position - self._states[second].position))


def make_env(config=None):
    config_path = Path(__file__).with_name("env_config.yaml")
    base = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base.update(config or {})
    return DroneRingEnv(base)
"""


def model_md(task_id: str, formalism: str) -> str:
    return (
        f"# Scenario Model: {task_id}\n\n"
        "## Formalism\n\n"
        f"{formalism}\n\n"
        "## Summary\n\n"
        "Simplified red-blue drone ring game for M1 contract testing.\n"
    )


def assumptions_md(assumptions: list[str]) -> str:
    lines = ["# Assumptions", ""]
    if assumptions:
        lines.extend(f"- {item}" for item in assumptions)
    else:
        lines.append("- No missing task parameters were filled by defaults.")
    return "\n".join(lines) + "\n"


def reset_deterministic_test_py() -> str:
    return """import sys
from pathlib import Path

import numpy as np

SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_reset_is_deterministic():
    env = make_env()
    first_obs, _ = env.reset(seed=7)
    second_obs, _ = env.reset(seed=7)
    for agent_id in env.agents:
        np.testing.assert_allclose(first_obs[agent_id], second_obs[agent_id])
"""


def obs_action_shape_test_py() -> str:
    return """import sys
from pathlib import Path

SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_obs_action_shapes_match_contract():
    env = make_env()
    observations, _ = env.reset(seed=1)
    assert tuple(env.observation_shape) == (12,)
    assert tuple(env.action_shape) == (4,)
    assert all(obs.shape == env.observation_shape for obs in observations.values())
"""
