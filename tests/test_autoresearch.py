from pathlib import Path
import csv

import pytest

from game_agent.autoresearch import AutoResearchRunner
from game_agent.autoresearch.metrics import ranking_key, satisfies_hard_constraints
from game_agent.autoresearch.runner import evaluate_policy_dir
from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_yaml, write_yaml


def test_autoresearch_generates_experiment_package(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截，超时 60 步", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp_dir = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    for name in ["leaderboard.csv", "best_config.yaml", "report.md", "manifest.json"]:
        assert (exp_dir / name).exists()
    assert "speed_scale" in read_yaml(exp_dir / "best_config.yaml")


def test_leaderboard_contains_primary_metric(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_002")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v2")
    exp_dir = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_002")
    text = (exp_dir / "leaderboard.csv").read_text(encoding="utf-8")
    assert "success_rate" in text
    assert "collision_rate" in text


def test_evaluate_policy_dir_returns_infer_compatible_metrics(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_003")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v3")

    result = evaluate_policy_dir(policy, scenario, seeds=[0])

    assert "raw_metrics" in result
    metrics = result["metrics"]
    assert metrics["primary"]["name"] == "success_rate"
    assert metrics["primary"]["direction"] == "maximize"
    assert isinstance(metrics["primary"]["value"], float)
    assert "avg_episode_length" in metrics["secondary"]
    assert "collision_rate" in metrics["hard_constraints"]
    assert {"value", "max", "passed"} <= set(metrics["hard_constraints"]["collision_rate"])


def test_autoresearch_rejects_unsupported_primary_metric(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_004")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v4")
    spec = read_yaml(scenario / "task_spec.yaml")
    spec["evaluation_metrics"]["primary"]["name"] = "custom_score"
    write_yaml(scenario / "task_spec.yaml", spec)

    with pytest.raises(KeyError, match="custom_score"):
        AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_004")


def test_hard_constraint_missing_metric_raises() -> None:
    evaluation_metrics = {"hard_constraints": [{"name": "collision_rate", "max": 0.1}]}

    with pytest.raises(KeyError, match="collision_rate"):
        satisfies_hard_constraints({"success_rate": 1.0}, evaluation_metrics)


def test_ranking_key_missing_primary_metric_raises() -> None:
    evaluation_metrics = {"primary": {"name": "custom_score", "direction": "maximize"}}

    with pytest.raises(KeyError, match="custom_score"):
        ranking_key({"success_rate": 1.0, "avg_episode_length": 3.0}, evaluation_metrics)


def test_best_config_matches_leaderboard_first_row(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_005")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v5")
    exp_dir = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_005")

    with (exp_dir / "leaderboard.csv").open("r", encoding="utf-8", newline="") as handle:
        first_row = next(csv.DictReader(handle))

    assert read_yaml(exp_dir / "best_config.yaml") == read_yaml(exp_dir / "trials" / first_row["trial_id"] / "config.yaml")
