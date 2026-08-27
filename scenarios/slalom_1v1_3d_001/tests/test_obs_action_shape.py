from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_obs_action_shapes_match_contract() -> None:
    env = make_env()
    observations, infos = env.reset(seed=1)
    assert tuple(env.observation_shape) == (64,)
    assert tuple(env.action_shape) == (3,)
    assert set(observations) == set(env.agents)
    assert all(obs.shape == env.observation_shape for obs in observations.values())
    assert all("metrics" in info for info in infos.values())


def test_zero_action_step_returns_stable_structure() -> None:
    env = make_env()
    observations, _ = env.reset(seed=1)
    zeros = {agent_id: np.zeros(env.action_shape, dtype=np.float32) for agent_id in env.agents}
    next_obs, rewards, terminations, truncations, infos = env.step(zeros)
    assert set(next_obs) == set(observations)
    assert set(rewards) == set(env.agents)
    assert set(terminations) == set(env.agents)
    assert set(truncations) == set(env.agents)
    assert all("action_clipped" in info for info in infos.values())
