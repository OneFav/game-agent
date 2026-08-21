from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


POLICY_DIR = Path(__file__).resolve().parents[1]
ENV_SPEC = {
    "action_space": {"shape": [3], "low": [-10.0, -10.0, -10.0], "high": [10.0, 10.0, 10.0]},
    "observation_space": {"shape": [94]},
}


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_vertical_wave_policy_bounds", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_actions_are_shape_three_and_clipped_for_all_roles() -> None:
    policy = load_policy_class()({}, ENV_SPEC)
    obs = np.zeros(94, dtype=np.float32)
    obs[46:49] = np.array([5.0, 1.0, 0.5], dtype=np.float32)
    obs[3:6] = np.array([20.0, -20.0, 5.0], dtype=np.float32)
    for agent_id in (
        "red_racer_0",
        "red_racer_1",
        "red_defender_0",
        "blue_racer_0",
        "blue_racer_1",
        "blue_defender_0",
    ):
        action = policy.act({agent_id: obs}, agent_id)
        assert action.shape == (3,)
        assert action.dtype == np.float32
        assert np.all(action >= -10.0)
        assert np.all(action <= 10.0)
