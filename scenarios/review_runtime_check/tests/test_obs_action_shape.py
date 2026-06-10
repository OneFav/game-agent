import sys
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
