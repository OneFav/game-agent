from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SCENARIO_DIR = Path(__file__).resolve().parents[1]


def _load_env_module():
    spec = importlib.util.spec_from_file_location("figure_eight_4v4_env", SCENARIO_DIR / "env.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reset_seed_is_deterministic() -> None:
    env_module = _load_env_module()
    env = env_module.make_env()
    first_obs, _first_info = env.reset(seed=7)
    second_obs, _second_info = env.reset(seed=7)
    assert first_obs.keys() == second_obs.keys()
    for agent_id in first_obs:
        np.testing.assert_allclose(first_obs[agent_id], second_obs[agent_id])
