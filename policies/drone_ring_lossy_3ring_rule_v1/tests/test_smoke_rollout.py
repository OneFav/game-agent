from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy import PolicyClass


def test_policy_smoke_rollout_action_shape_and_bounds() -> None:
    env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
    policy = PolicyClass({}, env_spec)
    action = policy.act(np.zeros(12, dtype=np.float32), "red_0")

    assert action.shape == (4,)
    assert np.all(np.isfinite(action))
    assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
    assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))
