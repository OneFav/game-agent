from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from env import make_env


def test_reset_is_deterministic() -> None:
    env = make_env()
    first_obs, _ = env.reset(seed=7)
    second_obs, _ = env.reset(seed=7)
    for agent_id in env.agents:
        np.testing.assert_allclose(first_obs[agent_id], second_obs[agent_id])
