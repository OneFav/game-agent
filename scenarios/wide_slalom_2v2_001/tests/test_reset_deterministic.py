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
    for agent_id in env.agents:
        np.testing.assert_array_equal(first_obs[agent_id], second_obs[agent_id])
        assert first_infos[agent_id]["collision"] == second_infos[agent_id]["collision"]
        assert first_infos[agent_id]["out_of_bounds"] == second_infos[agent_id]["out_of_bounds"]
        assert first_infos[agent_id]["gate_passed_count"] == second_infos[agent_id]["gate_passed_count"]
        assert first_infos[agent_id]["team_scores"] == second_infos[agent_id]["team_scores"]
