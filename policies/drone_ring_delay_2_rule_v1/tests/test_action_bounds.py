from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy import PolicyClass


def test_policy_actions_respect_bounds() -> None:
    env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
    policy = PolicyClass({"speed_scale": 10.0, "intercept_gain": 10.0}, env_spec)
    for agent_id in ("red_0", "blue_0"):
        action = policy.act(np.ones(12, dtype=np.float32), agent_id)
        assert action.shape == (4,)
        assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
        assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))


def test_safety_margin_avoids_close_opponent_for_red() -> None:
    env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
    obs = np.zeros(12, dtype=np.float32)
    obs[4:6] = [0.0, 0.05]
    obs[9:11] = [1.0, 0.0]

    no_margin = PolicyClass({"speed_scale": 1.0, "safety_margin": 0.0}, env_spec).act(obs, "red_0")
    with_margin = PolicyClass({"speed_scale": 1.0, "safety_margin": 1.0}, env_spec).act(obs, "red_0")

    assert with_margin[1] < no_margin[1]
