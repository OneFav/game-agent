from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

POLICY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POLICY_DIR))

from policy import PolicyClass  # noqa: E402


SPEC = {
    "observation_space": {"shape": [12]},
    "action_space": {
        "shape": [4],
        "low": [-2.0, -2.0, -1.0, -1.0],
        "high": [2.0, 2.0, 1.0, 1.0],
    },
}


def test_untrained_policy_actions_are_finite_and_bounded() -> None:
    policy = PolicyClass({}, SPEC)
    policy.reset(7)
    observations = {
        "red_0": np.zeros(12, dtype=np.float32),
        "blue_0": np.zeros(12, dtype=np.float32),
    }
    for agent_id in observations:
        action = policy.act(observations, agent_id)
        assert action.shape == (4,)
        assert np.all(np.isfinite(action))
        assert np.all(action >= np.asarray(SPEC["action_space"]["low"]))
        assert np.all(action <= np.asarray(SPEC["action_space"]["high"]))


def test_policy_declares_only_stage_one_search_fields() -> None:
    schema = PolicyClass({}, SPEC).get_config_schema()
    assert set(schema) == {"learning_rate", "progress_reward_weight"}
