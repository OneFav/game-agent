from __future__ import annotations

import sys
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def _policy() -> PolicyClass:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    return PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})


def test_reset_is_deterministic() -> None:
    obs = np.asarray([0, 0, 0.1, -0.2, 1.0, 0.4, 0, 0, 1, 0], dtype=np.float32)
    policy = _policy()
    policy.reset(17)
    first = policy.act({"agent_00": obs}, "agent_00")
    policy.reset(17)
    second = policy.act({"agent_00": obs}, "agent_00")
    assert np.array_equal(first, second)


def test_checkpoint_dimension_mismatch_is_rejected() -> None:
    policy = _policy()
    payload = '{"policy_id": "' + policy.config["policy_id"] + '", "action_shape": [3]}'
    with patch("game_agent.policy_designer.max_space_policy.Path") as path_type:
        path_type.return_value.is_file.return_value = True
        path_type.return_value.read_text.return_value = payload
        with pytest.raises(ValueError, match="shape mismatch"):
            policy.load("synthetic-mismatch.json")
