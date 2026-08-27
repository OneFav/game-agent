from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy import PolicyClass


def test_act_has_no_io_or_input_mutation(capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    obs = {"agent_00": np.asarray([0, 0, 0, 0, 1, 0, 0, 0, 1, 0], dtype=np.float32)}
    snapshot = obs["agent_00"].copy()
    before = {path.relative_to(root) for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    started = time.perf_counter()
    for _ in range(100):
        policy.act(obs, "agent_00")
    elapsed = time.perf_counter() - started
    assert np.array_equal(obs["agent_00"], snapshot)
    after = {path.relative_to(root) for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    assert after == before
    assert capsys.readouterr().out == ""
    assert elapsed < 5.0
