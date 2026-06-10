import sys
from pathlib import Path

import numpy as np

SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_reset_is_deterministic():
    env = make_env()
    first_obs, first_infos = env.reset(seed=7)
    second_obs, second_infos = env.reset(seed=7)
    assert first_infos == second_infos
    for agent_id in env.agents:
        np.testing.assert_array_equal(first_obs[agent_id], second_obs[agent_id])
