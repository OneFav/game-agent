from pathlib import Path

import yaml

from contracts.policy_protocol import Policy


def test_scenario_schema_declares_required_top_level_fields() -> None:
    data = yaml.safe_load(Path("contracts/scenario_schema.yaml").read_text(encoding="utf-8"))
    assert {"task_id", "task_family", "reward_structure", "evaluation_metrics"}.issubset(set(data["required"]))


def test_policy_protocol_defines_required_methods() -> None:
    for method in {"reset", "act", "load", "get_config_schema"}:
        assert method in Policy.__abstractmethods__
