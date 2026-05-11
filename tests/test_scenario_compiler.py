import os
from pathlib import Path
import subprocess
import sys

from game_agent.scenario_compiler import ScenarioCompiler
from game_agent.utils.fs import read_yaml


def test_compile_creates_scenario_package(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile(
        task_text="红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 80 步",
        task_id="drone_ring_001",
    )
    assert (scenario_dir / "task_spec.yaml").exists()
    assert (scenario_dir / "model.md").exists()
    assert (scenario_dir / "env.py").exists()
    assert (scenario_dir / "assumptions.md").exists()
    assert (scenario_dir / "manifest.json").exists()
    spec = read_yaml(scenario_dir / "task_spec.yaml")
    assert spec["task_family"] == "drone_ring_game"
    assert spec["env_config"]["ring_count"] == 2
    assert spec["env_config"]["max_steps"] == 80
    assert spec["communication"]["mode"] == "delayed"


def test_compile_records_assumptions_for_missing_values(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机追逃穿环", "drone_ring_002")
    assumptions = (scenario_dir / "assumptions.md").read_text(encoding="utf-8")
    assert "ring_count" in assumptions
    assert "max_steps" in assumptions
    assert "communication.mode" in assumptions


def test_generated_scenario_contract_tests_are_runnable_from_scenario_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scenario_dir = ScenarioCompiler(project_root=project_root).compile(
        "红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 80 步",
        "drone_ring_runnable",
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=scenario_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_make_env_loads_default_config_and_allows_overrides(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile(
        "红方无人机穿过三个圆环，超时 90 步",
        "drone_ring_config",
    )
    script = f"""
import sys
from pathlib import Path
scenario_root = Path({str(scenario_dir)!r})
sys.path.insert(0, str(scenario_root))
from env import make_env

default_env = make_env()
overridden_env = make_env({{"max_steps": 30}})
assert default_env.ring_count == 3
assert default_env.max_steps == 90
assert overridden_env.ring_count == 3
assert overridden_env.max_steps == 30
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_task_spec_contains_bounds_and_structured_metrics(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机追击穿过两环，超时 80 步", "drone_ring_contract")
    spec = read_yaml(scenario_dir / "task_spec.yaml")

    assert spec["observation_space"]["low"] == [-10.0] * 12
    assert spec["observation_space"]["high"] == [10.0] * 12
    assert spec["action_space"]["low"] == [-2.0, -2.0, -1.0, -1.0]
    assert spec["action_space"]["high"] == [2.0, 2.0, 1.0, 1.0]
    assert spec["action_space"]["semantics"] == "velocity_setpoint"
    description = spec["action_space"]["description"]
    assert description
    assert "vx" in description
    assert "vy" in description
    assert "vz" in description
    assert "yaw_rate" in description
    assert "ax" not in description
    assert spec["evaluation_metrics"]["primary"]["direction"] == "maximize"
    assert {item["name"] for item in spec["evaluation_metrics"]["secondary"]} >= {"collision_rate", "timeout_rate"}
    hard_constraints = {item["name"]: item for item in spec["evaluation_metrics"]["hard_constraints"]}
    assert hard_constraints["collision_rate"]["max"] == 0.05
    assert hard_constraints["out_of_bounds_rate"]["max"] == 0.01
    assert hard_constraints["action_violation_rate"]["max"] == 0.0
    assert all("threshold" not in constraint for constraint in hard_constraints.values())


def test_non_timeout_step_instruction_does_not_set_max_steps(tmp_path: Path) -> None:
    scenario_dir = ScenarioCompiler(project_root=tmp_path).compile("红方前10步保持悬停，然后穿过两环", "drone_ring_hover")
    spec = read_yaml(scenario_dir / "task_spec.yaml")
    assumptions = (scenario_dir / "assumptions.md").read_text(encoding="utf-8")

    assert spec["env_config"]["max_steps"] == 200
    assert "max_steps" in assumptions


def test_communication_defaults_are_recorded(tmp_path: Path) -> None:
    delayed_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机通信延迟后追逃穿过两环，超时 80 步", "delay_default")
    lossy_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机丢包后追逃穿过两环，超时 80 步", "lossy_default")
    percent_dir = ScenarioCompiler(project_root=tmp_path).compile("红蓝无人机丢包30%后追逃穿过两环，超时 80 步", "lossy_percent")

    delayed_spec = read_yaml(delayed_dir / "task_spec.yaml")
    lossy_spec = read_yaml(lossy_dir / "task_spec.yaml")
    percent_spec = read_yaml(percent_dir / "task_spec.yaml")
    delayed_assumptions = (delayed_dir / "assumptions.md").read_text(encoding="utf-8")
    lossy_assumptions = (lossy_dir / "assumptions.md").read_text(encoding="utf-8")

    assert delayed_spec["communication"] == {"mode": "delayed", "delay_steps": 1}
    assert "delay_steps" in delayed_assumptions
    assert lossy_spec["communication"] == {"mode": "lossy", "drop_probability": 0.1}
    assert "drop_probability" in lossy_assumptions
    assert percent_spec["communication"] == {"mode": "lossy", "drop_probability": 0.3}
