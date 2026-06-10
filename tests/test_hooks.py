import subprocess
import sys
from pathlib import Path

import yaml

from game_agent.autoresearch import AutoResearchRunner
from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler


SCENARIO_HOOK = [sys.executable, "src/hooks/post_scenario_compile.py"]
POLICY_HOOK = [sys.executable, "src/hooks/post_policy_submit.py"]
EXPERIMENT_HOOK = [sys.executable, "src/hooks/post_experiment_run.py"]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _assert_hook_fails(command: list[str], expected_error: str) -> None:
    result = _run(command)
    assert result.returncode == 1, result.stdout
    assert expected_error in result.stderr


def test_hooks_accept_valid_generated_packages(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    commands = [
        [*SCENARIO_HOOK, "--scenario", str(scenario)],
        [*POLICY_HOOK, "--policy", str(policy)],
        [*EXPERIMENT_HOOK, "--exp", str(exp)],
    ]
    for command in commands:
        result = _run(command)
        assert result.returncode == 0, result.stderr


def test_scenario_hook_rejects_empty_task_spec(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    (scenario / "task_spec.yaml").write_text("", encoding="utf-8")

    _assert_hook_fails([*SCENARIO_HOOK, "--scenario", str(scenario)], "task_spec.yaml must not be empty")


def test_policy_hook_rejects_fake_local_contract(tmp_path: Path) -> None:
    policy = tmp_path / "policies" / "fake_contract_policy"
    (policy / "contracts").mkdir(parents=True)
    (policy / "contracts" / "__init__.py").write_text("", encoding="utf-8")
    (policy / "contracts" / "policy_protocol.py").write_text(
        "class Policy:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (policy / "policy.py").write_text(
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "contract_path = Path(__file__).resolve().parent / 'contracts' / 'policy_protocol.py'\n"
        "spec = importlib.util.spec_from_file_location('fake_policy_contract', contract_path)\n"
        "fake_contract = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(fake_contract)\n\n"
        "class PolicyClass(fake_contract.Policy):\n"
        "    def __init__(self, config=None, env_spec=None):\n"
        "        pass\n"
        "    def reset(self, seed):\n"
        "        pass\n"
        "    def act(self, obs, agent_id, info=None):\n"
        "        return [0, 0, 0, 0]\n"
        "    def load(self, checkpoint_path):\n"
        "        pass\n"
        "    def get_config_schema(self):\n"
        "        return {'speed_scale': {'type': 'number'}}\n",
        encoding="utf-8",
    )
    _write_minimal_policy_files(policy, {"parameters": {"speed_scale": {"values": [1.0]}}})

    _assert_hook_fails([*POLICY_HOOK, "--policy", str(policy)], "PolicyClass must subclass real contracts Policy")


def test_policy_hook_rejects_search_space_field_missing_from_schema(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    search_space = yaml.safe_load((policy / "search_space.yaml").read_text(encoding="utf-8"))
    search_space["parameters"]["unknown_knob"] = {"values": [1]}
    (policy / "search_space.yaml").write_text(yaml.safe_dump(search_space), encoding="utf-8")

    _assert_hook_fails([*POLICY_HOOK, "--policy", str(policy)], "unknown_knob")


def test_policy_hook_accepts_policy_that_requires_env_spec(tmp_path: Path) -> None:
    policy = tmp_path / "policies" / "env_spec_policy"
    policy.mkdir(parents=True)
    (policy / "policy.py").write_text(
        "from contracts.policy_protocol import Policy\n\n"
        "class PolicyClass(Policy):\n"
        "    def __init__(self, config, env_spec):\n"
        "        self.action_low = env_spec['action_space']['low']\n"
        "        self.config = config\n"
        "    def reset(self, seed):\n"
        "        pass\n"
        "    def act(self, obs, agent_id, info=None):\n"
        "        return self.action_low\n"
        "    def load(self, checkpoint_path):\n"
        "        pass\n"
        "    def get_config_schema(self):\n"
        "        return {'speed_scale': {'type': 'number'}}\n",
        encoding="utf-8",
    )
    _write_minimal_policy_files(policy, {"parameters": {"speed_scale": {"values": [1.0]}}})

    result = _run([*POLICY_HOOK, "--policy", str(policy)])

    assert result.returncode == 0, result.stderr


def test_experiment_hook_rejects_empty_leaderboard(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    (exp / "leaderboard.csv").write_text("rank,trial_id,success_rate\n", encoding="utf-8")

    _assert_hook_fails([*EXPERIMENT_HOOK, "--exp", str(exp)], "leaderboard.csv must contain at least one data row")


def test_experiment_hook_rejects_trial_missing_file(tmp_path: Path) -> None:
    scenario = ScenarioCompiler(tmp_path).compile("红方穿过两个圆环，蓝方追击拦截", "drone_ring_001")
    policy = PolicyDesigner(tmp_path).build(scenario, "rule_ring_nav_v1")
    exp = AutoResearchRunner(tmp_path).run(scenario, policy, "exp_drone_ring_001")
    first_trial = next((exp / "trials").iterdir())
    (first_trial / "metrics.json").unlink()

    _assert_hook_fails([*EXPERIMENT_HOOK, "--exp", str(exp)], "missing required file: metrics.json")


def _write_minimal_policy_files(policy: Path, search_space: dict) -> None:
    for filename in ("train.py", "infer.py"):
        (policy / filename).write_text("", encoding="utf-8")
    (policy / "default_config.yaml").write_text("speed_scale: 1.0\n", encoding="utf-8")
    (policy / "search_space.yaml").write_text(yaml.safe_dump(search_space), encoding="utf-8")
    (policy / "algorithm_card.md").write_text("# Algorithm\n", encoding="utf-8")
    (policy / "requirements.txt").write_text("", encoding="utf-8")
    (policy / "manifest.json").write_text("{}\n", encoding="utf-8")
