from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


POLICY_DIR = Path(__file__).resolve().parents[1]
ENV_SPEC = {
    "action_space": {"shape": [3], "low": [-1.0, -1.0, -1.0], "high": [1.0, 1.0, 1.0]},
    "observation_space": {"shape": [64]},
}


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_slalom_policy_bounds", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_actions_are_shape_three_and_clipped_for_both_roles() -> None:
    policy = load_policy_class()({}, ENV_SPEC)
    obs = np.zeros(64, dtype=np.float32)
    obs[12:15] = np.array([10.0, 0.0, 1.0], dtype=np.float32)
    obs[6:9] = np.array([0.3, -0.2, 0.1], dtype=np.float32)
    obs[9:12] = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    obs[25] = 1.0
    for agent_id in ("red_racer_0", "blue_racer_0"):
        action = policy.act({agent_id: obs}, agent_id)
        assert action.shape == (3,)
        assert action.dtype == np.float32
        assert np.all(action >= -1.0)
        assert np.all(action <= 1.0)


def test_actions_accept_hook_style_12d_observation() -> None:
    policy = load_policy_class()({}, {"action_space": {"shape": [3], "low": [-1.0] * 3, "high": [1.0] * 3}})
    obs = np.array([0.0, 0.0, 0.1, -0.2, 1.0, 0.5, -0.3, 0.2, 0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    action = policy.act({"red_racer_0": obs}, "red_racer_0")
    assert action.shape == (3,)
    assert np.all(action >= -1.0)
    assert np.all(action <= 1.0)
