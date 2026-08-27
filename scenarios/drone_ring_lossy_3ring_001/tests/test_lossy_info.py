import sys
from pathlib import Path

import numpy as np

SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_packet_loss_flags_are_seed_deterministic():
    env = make_env()
    first_obs, first_info = env.reset(seed=11)
    second_obs, second_info = env.reset(seed=11)

    for agent_id in env.agents:
        np.testing.assert_allclose(first_obs[agent_id], second_obs[agent_id])
    assert first_info["communication_dropped"] == second_info["communication_dropped"]
