import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_TEXT = "红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 60 步"


def _pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(REPO_ROOT) if not current else f"{REPO_ROOT}{os.pathsep}{current}"
    return env


def test_cli_run_generates_full_m1_outputs(tmp_path: Path) -> None:
    non_repo_cwd = tmp_path / "non_repo_cwd"
    non_repo_cwd.mkdir()

    result = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "run",
            "--project-root", str(tmp_path),
            "--task", TASK_TEXT,
            "--task-id", "drone_ring_001",
            "--policy-id", "rule_ring_nav_v1",
            "--exp-id", "exp_drone_ring_001",
        ],
        text=True,
        capture_output=True,
        cwd=non_repo_cwd,
        env=_pythonpath_env(),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "scenarios" / "drone_ring_001" / "task_spec.yaml").exists()
    assert (tmp_path / "policies" / "rule_ring_nav_v1" / "policy.py").exists()
    assert (tmp_path / "experiments" / "exp_drone_ring_001" / "leaderboard.csv").exists()

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "drone_ring_game" in report
    assert "不是通用无人机仿真平台" in report
    assert "不是完整 RL 框架" in report

    task = (tmp_path / "task.md").read_text(encoding="utf-8")
    for section in [
        "Environment",
        "Scenario Compiler",
        "Policy Designer",
        "AutoResearch",
        "Validation",
        "Task family expansion",
    ]:
        assert section in task


def test_cli_compile_scenario_accepts_global_project_root(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "game_agent",
            "--project-root", str(tmp_path),
            "compile-scenario",
            "--task", TASK_TEXT,
            "--task-id", "global_root_scenario",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=_pythonpath_env(),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "scenarios" / "global_root_scenario" / "task_spec.yaml").exists()


def test_cli_step_commands_accept_ids_and_project_root_relative_paths(tmp_path: Path) -> None:
    compile_result = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "compile-scenario",
            "--project-root", str(tmp_path),
            "--task", TASK_TEXT,
            "--task-id", "step_scenario",
        ],
        text=True,
        capture_output=True,
        env=_pythonpath_env(),
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    build_by_id = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "build-policy",
            "--project-root", str(tmp_path),
            "--scenario", "step_scenario",
            "--policy-id", "step_policy_by_id",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path / "scenarios",
        env=_pythonpath_env(),
        check=False,
    )
    assert build_by_id.returncode == 0, build_by_id.stderr

    build_by_relative_path = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "build-policy",
            "--project-root", str(tmp_path),
            "--scenario", "scenarios/step_scenario",
            "--policy-id", "step_policy_by_relative_path",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path / "scenarios",
        env=_pythonpath_env(),
        check=False,
    )
    assert build_by_relative_path.returncode == 0, build_by_relative_path.stderr

    run_by_id = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "run-experiment",
            "--project-root", str(tmp_path),
            "--scenario", "step_scenario",
            "--policy", "step_policy_by_id",
            "--exp-id", "step_exp_by_id",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path / "policies",
        env=_pythonpath_env(),
        check=False,
    )
    assert run_by_id.returncode == 0, run_by_id.stderr

    run_by_relative_path = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "run-experiment",
            "--project-root", str(tmp_path),
            "--scenario", "scenarios/step_scenario",
            "--policy", "policies/step_policy_by_relative_path",
            "--exp-id", "step_exp_by_relative_path",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path / "policies",
        env=_pythonpath_env(),
        check=False,
    )
    assert run_by_relative_path.returncode == 0, run_by_relative_path.stderr

    assert (tmp_path / "experiments" / "step_exp_by_id" / "leaderboard.csv").exists()
    assert (tmp_path / "experiments" / "step_exp_by_relative_path" / "leaderboard.csv").exists()


def test_run_hook_failure_message_includes_diagnostics(tmp_path: Path) -> None:
    from game_agent.cli import _run_hook

    hook = tmp_path / "failing_hook.py"
    hook.write_text(
        "import sys\n"
        "print('hook stdout')\n"
        "print('hook stderr', file=sys.stderr)\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )

    try:
        _run_hook(hook, "--target", tmp_path)
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError("expected _run_hook to raise RuntimeError")

    assert str(hook) in message
    assert "exit code: 7" in message
    assert "stdout: hook stdout" in message
    assert "stderr: hook stderr" in message


def test_cli_failure_stderr_starts_with_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "game_agent", "build-policy",
            "--project-root", str(tmp_path),
            "--scenario", "missing_scenario",
            "--policy-id", "bad_policy",
        ],
        text=True,
        capture_output=True,
        env=_pythonpath_env(),
        check=False,
    )
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_cli_hook_failure_stderr_includes_diagnostics(tmp_path: Path, monkeypatch, capsys) -> None:
    import game_agent.cli as cli

    fake_repo_root = tmp_path / "fake_repo"
    hooks_dir = fake_repo_root / "hooks"
    hooks_dir.mkdir(parents=True)
    hook = hooks_dir / "post_scenario_compile.py"
    hook.write_text(
        "import sys\n"
        "print('hook stdout')\n"
        "print('hook stderr', file=sys.stderr)\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "REPO_ROOT", fake_repo_root)

    exit_code = cli.main(
        [
            "compile-scenario",
            "--project-root", str(tmp_path / "project"),
            "--task", TASK_TEXT,
            "--task-id", "hook_fail_scenario",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error:")
    assert "post_scenario_compile.py" in captured.err
    assert "exit code: 7" in captured.err
    assert "stdout: hook stdout" in captured.err
    assert "stderr: hook stderr" in captured.err
