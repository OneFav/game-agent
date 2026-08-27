from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


POLICY_DIR = Path(__file__).resolve().parents[1]


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_slalom_policy_side_effects", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_act_does_not_mutate_observation_or_write_files() -> None:
    policy = load_policy_class()()
    before_files = {path.relative_to(POLICY_DIR) for path in POLICY_DIR.rglob("*") if path.is_file()}
    obs = np.zeros(64, dtype=np.float32)
    obs[12:15] = np.array([6.0, 0.0, 0.0], dtype=np.float32)
    original = obs.copy()
    action = policy.act({"blue_racer_0": obs}, "blue_racer_0")
    after_files = {path.relative_to(POLICY_DIR) for path in POLICY_DIR.rglob("*") if path.is_file()}
    np.testing.assert_array_equal(obs, original)
    assert action.shape == (3,)
    assert before_files == after_files
