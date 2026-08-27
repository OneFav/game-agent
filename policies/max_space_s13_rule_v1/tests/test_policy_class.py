from __future__ import annotations

import inspect
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for parent in Path(__file__).resolve().parents:
    if (parent / "src" / "contracts" / "policy_protocol.py").is_file():
        sys.path.insert(0, str(parent / "src"))
        break

from contracts.policy_protocol import Policy
from policy import PolicyClass


def test_policy_class_implements_contract_and_schema() -> None:
    assert issubclass(PolicyClass, Policy)
    signature = inspect.signature(PolicyClass)
    signature.bind({}, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "default_config.yaml").read_text(encoding="utf-8"))
    policy = PolicyClass(config, {"action_space": {"shape": [2], "low": [-1, -1], "high": [1, 1]}})
    search = yaml.safe_load((Path(__file__).resolve().parents[1] / "search_space.yaml").read_text(encoding="utf-8"))
    schema = policy.get_config_schema()
    assert set(search["parameters"]) <= set(schema)
    assert set(search["priority_groups"]["do_not_tune"]) <= set(schema)
    assert policy.supports_training() is False
