from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SCENARIO_DIR = Path(__file__).resolve().parents[1]


def _load_env_module():
    spec = importlib.util.spec_from_file_location("figure_eight_4v4_env_shape", SCENARIO_DIR / "env.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_obs_and_action_shapes_match_contract() -> None:
    env_module = _load_env_module()
    env = env_module.make_env()
    observations, _infos = env.reset(seed=11)
    assert len(observations) == 8
    for agent_id, obs in observations.items():
        assert agent_id in env.agents
        assert obs.shape == (110,)
        assert obs.dtype == np.float32
        assert env.action_space(agent_id).shape == (3,)
