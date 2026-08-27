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
    spec = importlib.util.spec_from_file_location("tested_figure_eight_policy", POLICY_DIR / "policy.py")
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
