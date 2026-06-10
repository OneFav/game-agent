import sys
from pathlib import Path

import numpy as np

SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_obs_action_shapes_match_contract():
    env = make_env()
    observations, infos = env.reset(seed=1)
    assert env.agents == ["red_racer_0", "red_defender_0", "blue_racer_0", "blue_defender_0"]
    assert tuple(env.observation_shape) == (32,)
    assert tuple(env.action_shape) == (4,)
    assert all(obs.shape == env.observation_shape for obs in observations.values())
    assert env.observation_space("red_racer_0").shape == (32,)
    assert env.action_space("red_racer_0").shape == (4,)
    for info in infos.values():
        assert {"collision", "out_of_bounds", "ring_passed_count", "communication_dropped", "action_clipped"} <= set(info)


def test_step_accepts_four_agent_actions():
    env = make_env()
    env.reset(seed=2)
    actions = {agent_id: np.zeros(env.action_shape, dtype=np.float32) for agent_id in env.agents}
    observations, rewards, terminations, truncations, infos = env.step(actions)
    assert set(observations) == set(env.agents)
    assert set(rewards) == set(env.agents)
    assert set(terminations) == set(env.agents)
    assert set(truncations) == set(env.agents)
    assert set(infos) == set(env.agents)
