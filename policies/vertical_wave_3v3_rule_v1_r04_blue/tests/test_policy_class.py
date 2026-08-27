from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
POLICY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from contracts.policy_protocol import Policy


def load_policy_class() -> type:
    spec = importlib.util.spec_from_file_location("tested_vertical_wave_policy", POLICY_DIR / "policy.py")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.PolicyClass


def test_policy_class_subclasses_contract() -> None:
    policy_class = load_policy_class()
    assert issubclass(policy_class, Policy)
    policy = policy_class()
    assert policy.supports_training() is False
    for method in ("reset", "act", "load", "get_config_schema", "compute_actions"):
        assert callable(getattr(policy, method))


def test_round4_blue_freezes_round3_red_config() -> None:
    policy_class = load_policy_class()
    policy = policy_class({"red_desired_speed": 2.0, "blue_intercept_gain": 3.0})
    assert policy.config["red_desired_speed"] == 6.4
    assert policy.config["red_risk_margin"] == 0.8
    assert policy.config["red_lane_spacing"] == 1.6
    assert policy.config["red_defender_mode"] == "escort"
    assert policy.config["blue_intercept_gain"] == 3.0
    assert "blue_intercept_gain" in policy.get_config_schema()
