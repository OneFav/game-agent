from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


POLICY_DIR = Path(__file__).resolve().parents[1]
ENV_SPEC = {
    "action_space": {"shape": [4], "low": [-1.0, -1.0, -1.0, -1.0], "high": [1.0, 1.0, 1.0, 1.0]},
    "observation_space": {"shape": [12]},
}


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_policy_bounds", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_actions_are_shape_four_and_clipped_for_all_roles() -> None:
    policy = load_policy_class()({}, ENV_SPEC)
    obs = np.array([0.0, 0.0, -8.0, 8.0, 0.1, -0.1, 8.0, -8.0, 1.0, 10.0, -10.0, 80.0], dtype=np.float32)
    for agent_id in ("red_racer_0", "red_defender_0", "blue_defender_0", "blue_racer_0"):
        action = policy.act({agent_id: obs}, agent_id)
        assert action.shape == (4,)
        assert action.dtype == np.float32
        assert np.all(action >= -1.0)
        assert np.all(action <= 1.0)


def test_actions_accept_frozen_32d_observation() -> None:
    policy = load_policy_class()({}, {**ENV_SPEC, "observation_space": {"shape": [32]}})
    obs = np.zeros(32, dtype=np.float32)
    obs[16] = 1.0
    obs[17:19] = np.array([1.0, 0.0], dtype=np.float32)
    obs[19] = 10.0
    obs[26:28] = np.array([5.0, 2.0], dtype=np.float32)
    for agent_id in ("red_racer_0", "red_defender_0", "blue_defender_0", "blue_racer_0"):
        action = policy.act({agent_id: obs}, agent_id)
        assert action.shape == (4,)
        assert action.dtype == np.float32
        assert np.all(action >= -1.0)
        assert np.all(action <= 1.0)
