from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


POLICY_DIR = Path(__file__).resolve().parents[1]


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_slalom_policy_deterministic", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_reset_seed_keeps_action_deterministic() -> None:
    policy = load_policy_class()()
    obs = np.zeros(64, dtype=np.float32)
    obs[12:15] = np.array([4.0, 1.0, 0.5], dtype=np.float32)
    obs[6:9] = np.array([2.0, 1.0, 0.2], dtype=np.float32)
    obs[9:12] = np.array([-0.5, 0.2, 0.0], dtype=np.float32)
    obs[25] = 0.4
    policy.reset(123)
    first = policy.act({"red_racer_0": obs}, "red_racer_0")
    policy.reset(123)
    second = policy.act({"red_racer_0": obs}, "red_racer_0")
    np.testing.assert_array_equal(first, second)
