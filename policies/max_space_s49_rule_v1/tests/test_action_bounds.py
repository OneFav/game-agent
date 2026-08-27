from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def test_action_shape_finiteness_and_bounds() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    env_spec = {"action_space": {"shape": [3], "low": [-0.2, -0.3, -0.4], "high": [0.2, 0.3, 0.4]}}
    policy = PolicyClass(config, env_spec)
    obs = np.zeros(13, dtype=np.float32)
    obs[6:9] = [10.0, -10.0, 10.0]
    action = policy.act({"red_0": obs}, "red_0")
    assert action.shape == (3,)
    assert np.all(np.isfinite(action))
    assert np.all(action >= np.asarray(env_spec["action_space"]["low"], dtype=np.float32))
    assert np.all(action <= np.asarray(env_spec["action_space"]["high"], dtype=np.float32))


def test_exception_falls_back_to_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    assert np.array_equal(policy.act({}, "missing_agent"), np.zeros(2, dtype=np.float32))
