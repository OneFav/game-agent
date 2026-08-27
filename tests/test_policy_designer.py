from pathlib import Path
import subprocess
import sys

from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_json, read_yaml


def test_build_policy_package_from_scenario(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    for name in [
        "policy.py",
        "train.py",
        "infer.py",
        "default_config.yaml",
        "search_space.yaml",
        "algorithm_card.md",
        "requirements.txt",
        "metadata.json",
        "manifest.json",
    ]:
        assert (policy_dir / name).exists()
    for name in [
        "test_policy_interface.py",
        "test_action_bounds.py",
        "test_inference_latency.py",
        "test_smoke_rollout.py",
    ]:
        assert (policy_dir / "tests" / name).exists()
    assert read_yaml(policy_dir / "default_config.yaml")["policy_type"] == "rule_ring_navigation"
    metadata = read_json(policy_dir / "metadata.json")
    assert metadata["method"]["name"] == "rule_ring_navigation"
    assert metadata["method_hypothesis"]["statement"]
    assert metadata["method_hypothesis"]["optimization_guidance"]
    assert metadata["immutable_boundaries"]["evaluation_source"] == "scenario.evaluation_metrics"
    assert metadata["immutable_boundaries"]["method_invariants"]
    assert metadata["checkpoint_binding"]["observation_contract"] == "scenario.observation_space"


def test_policy_search_space_contains_autoresearch_fields(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_002")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v2")
    search_space = read_yaml(policy_dir / "search_space.yaml")
    assert "speed_scale" in search_space["parameters"]
    assert "intercept_gain" in search_space["parameters"]


def test_generated_policy_tests_run_inside_policy_dir(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_003")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v3")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-v"],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_infer_help_runs_inside_policy_dir(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_004")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v4")

    result = subprocess.run(
        [sys.executable, "infer.py", "--help"],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for option in ["--checkpoint", "--scenario", "--eval_seeds", "--output", "--render", "--stress_test"]:
        assert option in result.stdout
    assert "--stress_test STRESS_TEST" in result.stdout


def test_generated_infer_runs_minimal_evaluation(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_006")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v6")
    output = tmp_path / "eval_results.json"
    checkpoint = tmp_path / "checkpoint_final.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "infer.py",
            "--checkpoint",
            checkpoint.as_posix(),
            "--scenario",
            scenario.as_posix(),
            "--eval_seeds",
            "10,11",
            "--output",
            output.as_posix(),
            "--stress_test",
            "nominal",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    results = read_json(output)
    expected_keys = {
        "policy_id",
        "checkpoint_hash",
        "scenario_id",
        "seeds_evaluated",
        "n_episodes",
        "metrics",
        "per_seed_metrics",
        "failure_episodes",
        "wall_time_seconds",
        "stress_test",
    }
    assert expected_keys <= set(results)
    assert results["policy_id"] == "rule_ring_nav_v6"
    assert results["checkpoint_hash"].startswith("sha256:")
    assert results["scenario_id"] == "drone_ring_006"
    assert results["seeds_evaluated"] == [10, 11]
    assert results["n_episodes"] == 2
    assert results["stress_test"] == "nominal"
    assert results["metrics"]["primary"]["name"] == "success_rate"
    assert "value" in results["metrics"]["primary"]
    assert results["metrics"]["primary"]["direction"] == "maximize"
    for key in ["mean", "std", "n"]:
        assert key in results["metrics"]["primary"]
    avg_episode_length = results["metrics"]["secondary"]["avg_episode_length"]
    assert isinstance(avg_episode_length, dict)
    for key in ["value", "mean", "std", "direction"]:
        assert key in avg_episode_length
    for name in ["collision_rate", "out_of_bounds_rate", "action_violation_rate"]:
        assert "max" in results["metrics"]["hard_constraints"][name]
        assert "passed" in results["metrics"]["hard_constraints"][name]
    assert len(results["per_seed_metrics"]) == 2
    for item in results["per_seed_metrics"]:
        for key in [
            "seed",
            "success_rate",
            "collision_rate",
            "out_of_bounds_rate",
            "episode_length",
            "action_violation_rate",
        ]:
            assert key in item


def test_generated_infer_rejects_missing_checkpoint(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_007")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v7")
    output = tmp_path / "missing_checkpoint_eval.json"

    result = subprocess.run(
        [
            sys.executable,
            "infer.py",
            "--checkpoint",
            (tmp_path / "missing_checkpoint.pt").as_posix(),
            "--scenario",
            scenario.as_posix(),
            "--eval_seeds",
            "10",
            "--output",
            output.as_posix(),
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "checkpoint" in result.stderr.lower()
    assert not output.exists()


def test_generated_infer_metrics_follow_task_spec(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_008")
    task_spec_path = scenario / "task_spec.yaml"
    task_spec = read_yaml(task_spec_path)
    task_spec["evaluation_metrics"]["primary"]["name"] = "custom_primary_metric"
    task_spec["evaluation_metrics"]["primary"]["direction"] = "minimize"
    for constraint in task_spec["evaluation_metrics"]["hard_constraints"]:
        if constraint["name"] == "collision_rate":
            constraint["max"] = 0.2
    from game_agent.utils.fs import write_yaml

    write_yaml(task_spec_path, task_spec)

    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v8")
    checkpoint = tmp_path / "checkpoint_final.pt"
    checkpoint.write_text("checkpoint", encoding="utf-8")
    output = tmp_path / "custom_metrics_eval.json"

    result = subprocess.run(
        [
            sys.executable,
            "infer.py",
            "--checkpoint",
            checkpoint.as_posix(),
            "--scenario",
            scenario.as_posix(),
            "--eval_seeds",
            "10",
            "--output",
            output.as_posix(),
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    results = read_json(output)
    assert results["metrics"]["primary"]["name"] == "custom_primary_metric"
    assert results["metrics"]["primary"]["direction"] == "minimize"
    assert results["metrics"]["hard_constraints"]["collision_rate"]["max"] == 0.2


def test_generated_train_validates_inputs(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红蓝无人机穿环", "drone_ring_005")
    policy_dir = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v5")
    output_dir = tmp_path / "training_output"

    valid = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "default_config.yaml",
            "--scenario",
            scenario.as_posix(),
            "--seed",
            "7",
            "--output_dir",
            output_dir.as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "30",
            "--log_interval",
            "5",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert valid.returncode == 0, valid.stdout + valid.stderr
    for name in ["checkpoint_final.pt", "training_curves.csv", "training_log.json", "stdout.log"]:
        assert (output_dir / name).exists()
    curve_header = (output_dir / "training_curves.csv").read_text(encoding="utf-8").splitlines()[0]
    assert curve_header.split(",") == [
        "step",
        "episode",
        "reward_mean",
        "actor_loss",
        "critic_loss",
        "evaluation_primary",
    ]
    training_log = read_json(output_dir / "training_log.json")
    for key in [
        "schema_version",
        "policy_id",
        "scenario_id",
        "termination_reason",
        "checkpoint_path",
        "checkpoint_hash",
        "status",
        "config_used",
        "seed",
        "started_at",
        "finished_at",
        "wall_time_seconds",
        "total_steps",
        "final_train_metrics",
    ]:
        assert key in training_log
    assert training_log["termination_reason"] == "max_steps_reached"
    assert training_log["checkpoint_path"] == "checkpoint_final.pt"
    assert training_log["checkpoint_hash"].startswith("sha256:")
    assert training_log["seed"] == 7
    assert training_log["total_steps"] == 10
    assert isinstance(training_log["wall_time_seconds"], float)
    assert isinstance(training_log["final_train_metrics"], dict)
    assert "mean_episode_reward" in training_log["final_train_metrics"]
    assert "mean_episode_length" in training_log["final_train_metrics"]
    assert training_log["started_at"]
    assert training_log["finished_at"]
    assert (output_dir / "training_log.json").exists()

    default_log_interval_output = tmp_path / "default_log_interval_output"
    default_log_interval = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "default_config.yaml",
            "--scenario",
            scenario.as_posix(),
            "--seed",
            "7",
            "--output_dir",
            default_log_interval_output.as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "30",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert default_log_interval.returncode == 0, default_log_interval.stdout + default_log_interval.stderr
    assert read_json(default_log_interval_output / "training_log.json")["log_interval"] == 1000

    timeout_output = tmp_path / "timeout_output"
    timeout = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "default_config.yaml",
            "--scenario",
            scenario.as_posix(),
            "--seed",
            "7",
            "--output_dir",
            timeout_output.as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "0",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert timeout.returncode == 2, timeout.stdout + timeout.stderr
    assert read_json(timeout_output / "training_log.json")["termination_reason"] == "wall_time_exhausted"

    invalid_config = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "missing.yaml",
            "--scenario",
            scenario.as_posix(),
            "--seed",
            "7",
            "--output_dir",
            (tmp_path / "bad_config_output").as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "30",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert invalid_config.returncode == 3
    assert not (tmp_path / "bad_config_output" / "training_log.json").exists()

    invalid_scenario = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "default_config.yaml",
            "--scenario",
            (tmp_path / "missing_scenario").as_posix(),
            "--seed",
            "7",
            "--output_dir",
            (tmp_path / "bad_scenario_output").as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "30",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert invalid_scenario.returncode == 3
    assert not (tmp_path / "bad_scenario_output" / "training_log.json").exists()

    invalid_resume = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--config",
            "default_config.yaml",
            "--scenario",
            scenario.as_posix(),
            "--seed",
            "7",
            "--resume_from",
            "missing_checkpoint.json",
            "--output_dir",
            (tmp_path / "bad_resume_output").as_posix(),
            "--max_steps",
            "10",
            "--wall_time_limit",
            "30",
        ],
        cwd=policy_dir,
        text=True,
        capture_output=True,
    )
    assert invalid_resume.returncode == 3
    assert not (tmp_path / "bad_resume_output" / "training_log.json").exists()
