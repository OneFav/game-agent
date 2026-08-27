from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy import PolicyClass


def test_policy_inference_latency_is_lightweight() -> None:
    env_spec = {"action_space": {"low": [-2.0, -2.0, -1.0, -1.0], "high": [2.0, 2.0, 1.0, 1.0]}}
    policy = PolicyClass({}, env_spec)
    obs = np.zeros(12, dtype=np.float32)

    start = time.perf_counter()
    for _ in range(100):
        policy.act(obs, "red_0")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5
