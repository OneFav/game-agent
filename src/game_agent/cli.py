from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from game_agent.autoresearch import AutoResearchRunner
from game_agent.policy_designer import PolicyDesigner
from game_agent.scenario_compiler import ScenarioCompiler


REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        project_root = Path(args.project_root).resolve()
        if args.command == "run":
            scenario_dir = _compile_scenario(project_root, args.task, args.task_id)
            policy_dir = _build_policy(project_root, scenario_dir, args.policy_id)
            exp_dir = _run_experiment(project_root, scenario_dir, policy_dir, args.exp_id)
            _write_root_report(project_root)
            _write_task_md(project_root)
            _print_paths(scenario_dir, policy_dir, exp_dir)
            return 0

        if args.command == "compile-scenario":
            scenario_dir = _compile_scenario(project_root, args.task, args.task_id)
            print(f"scenario: {scenario_dir}")
            return 0

        if args.command == "build-policy":
            scenario_dir = _resolve_artifact(project_root, "scenarios", args.scenario)
            policy_dir = _build_policy(project_root, scenario_dir, args.policy_id)
            print(f"policy: {policy_dir}")
            return 0

        if args.command == "run-experiment":
            scenario_dir = _resolve_artifact(project_root, "scenarios", args.scenario)
            policy_dir = _resolve_artifact(project_root, "policies", args.policy)
            exp_dir = _run_experiment(project_root, scenario_dir, policy_dir, args.exp_id)
            print(f"experiment: {exp_dir}")
            return 0

        parser.print_help()
        return 1
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Game Agent M1 orchestration CLI.")
    parser.add_argument("--project-root", default=".", help="Output project root.")

    project_root_parent = argparse.ArgumentParser(add_help=False)
    project_root_parent.add_argument("--project-root", default=argparse.SUPPRESS, help="Output project root.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", parents=[project_root_parent], help="Run the full M1 pipeline.")
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--task-id", required=True)
    run_parser.add_argument("--policy-id", required=True)
    run_parser.add_argument("--exp-id", required=True)

    compile_parser = subparsers.add_parser(
        "compile-scenario",
        parents=[project_root_parent],
        help="Compile a task into a scenario package.",
    )
    compile_parser.add_argument("--task", required=True)
    compile_parser.add_argument("--task-id", required=True)

    policy_parser = subparsers.add_parser(
        "build-policy",
        parents=[project_root_parent],
        help="Build a policy package for a scenario.",
    )
    policy_parser.add_argument("--scenario", required=True)
    policy_parser.add_argument("--policy-id", required=True)

    exp_parser = subparsers.add_parser(
        "run-experiment",
        parents=[project_root_parent],
        help="Run AutoResearch for a scenario and policy.",
    )
    exp_parser.add_argument("--scenario", required=True)
    exp_parser.add_argument("--policy", required=True)
    exp_parser.add_argument("--exp-id", required=True)

    return parser


def _compile_scenario(project_root: Path, task: str, task_id: str) -> Path:
    scenario_dir = ScenarioCompiler(project_root).compile(task, task_id)
    _run_hook(REPO_ROOT / "src" / "hooks" / "post_scenario_compile.py", "--scenario", scenario_dir)
    return scenario_dir


def _build_policy(project_root: Path, scenario_dir: Path, policy_id: str) -> Path:
    policy_dir = PolicyDesigner(project_root).build(scenario_dir, policy_id)
    _run_hook(REPO_ROOT / "src" / "hooks" / "post_policy_submit.py", "--policy", policy_dir)
    return policy_dir


def _run_experiment(project_root: Path, scenario_dir: Path, policy_dir: Path, exp_id: str) -> Path:
    exp_dir = AutoResearchRunner(project_root).run(scenario_dir, policy_dir, exp_id)
    _run_hook(REPO_ROOT / "src" / "hooks" / "post_experiment_run.py", "--exp", exp_dir)
    return exp_dir


def _run_hook(script: Path, flag: str, path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script), flag, str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "\n".join(
                [
                    f"hook failed: {script}",
                    f"exit code: {result.returncode}",
                    f"stdout: {result.stdout.strip()}",
                    f"stderr: {result.stderr.strip()}",
                ]
            )
        )


def _write_root_report(project_root: Path) -> Path:
    project_root.mkdir(parents=True, exist_ok=True)
    path = project_root / "report.md"
    path.write_text(
        "\n".join(
            [
                "# Game Agent M1 Report",
                "",
                "M1 \u652f\u6301\u7b80\u5316 `drone_ring_game` \u5782\u76f4\u94fe\u8def\uff1a\u7ea2\u65b9\u65e0\u4eba\u673a\u7a7f\u8fc7\u5706\u73af\uff0c\u84dd\u65b9\u65e0\u4eba\u673a\u8ffd\u51fb\u5e76\u5c1d\u8bd5\u62e6\u622a\uff0c"
                "\u573a\u666f\u53ef\u8868\u8fbe\u901a\u4fe1\u5ef6\u8fdf\u548c\u8d85\u65f6\u6b65\u6570\u3002",
                "",
                "\u5f53\u524d\u5b9e\u73b0\u4e0d\u662f\u901a\u7528\u65e0\u4eba\u673a\u4eff\u771f\u5e73\u53f0\uff0c\u4e5f\u4e0d\u662f\u5b8c\u6574 RL \u6846\u67b6\uff1b\u5b83\u53ea\u8986\u76d6 M1 \u6240\u9700\u7684\u573a\u666f\u7f16\u8bd1\u3001"
                "\u89c4\u5219\u7b56\u7565\u751f\u6210\u4e0e\u8f7b\u91cf AutoResearch \u8bc4\u4f30\u95ed\u73af\u3002",
                "",
                "\u540e\u7eed\u4efb\u52a1\u4e0e\u6269\u5c55\u8ba1\u5212\u89c1 [task.md](task.md)\u3002",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_task_md(project_root: Path) -> Path:
    project_root.mkdir(parents=True, exist_ok=True)
    path = project_root / "task.md"
    path.write_text(
        "\n".join(
            [
                "# Remaining Tasks",
                "",
                "## Environment",
                "- \u6269\u5c55 `drone_ring_game` \u7684\u52a8\u529b\u5b66\u3001\u78b0\u649e\u4e0e\u8fb9\u754c\u9a8c\u8bc1\u8986\u76d6\u3002",
                "",
                "## Scenario Compiler",
                "- \u589e\u5f3a\u81ea\u7136\u8bed\u8a00\u89e3\u6790\uff0c\u8865\u5145\u66f4\u591a\u4efb\u52a1\u5047\u8bbe\u4e0e schema \u6821\u9a8c\u3002",
                "",
                "## Policy Designer",
                "- \u652f\u6301\u66f4\u591a\u57fa\u7ebf\u7b56\u7565\u6a21\u677f\u4e0e\u53ef\u914d\u7f6e\u53c2\u6570\u7a7a\u95f4\u3002",
                "",
                "## AutoResearch",
                "- \u589e\u52a0\u5b9e\u9a8c\u9884\u7b97\u63a7\u5236\u3001\u91cd\u590d\u5b9e\u9a8c\u7edf\u8ba1\u4e0e\u7ed3\u679c\u5f52\u6863\u3002",
                "",
                "## Validation",
                "- \u5c06 hooks\u3001\u751f\u6210\u5305\u6d4b\u8bd5\u548c\u6839\u7ea7 smoke \u6d4b\u8bd5\u7eb3\u5165\u6301\u7eed\u9a8c\u8bc1\u3002",
                "",
                "## Task family expansion",
                "- \u5728\u4fdd\u6301\u63a5\u53e3\u7a33\u5b9a\u7684\u524d\u63d0\u4e0b\u6269\u5c55\u65b0\u7684\u4efb\u52a1\u65cf\u4e0e\u8bc4\u4f30\u6307\u6807\u3002",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _resolve_artifact(project_root: Path, collection: str, value: str) -> Path:
    project_root = Path(project_root).resolve()
    path = Path(value)
    if path.is_absolute():
        return path

    project_relative = project_root / path
    if project_relative.exists():
        return project_relative.resolve()

    return (project_root / collection / path).resolve()


def _print_paths(scenario_dir: Path, policy_dir: Path, exp_dir: Path) -> None:
    print(f"scenario: {scenario_dir}")
    print(f"policy: {policy_dir}")
    print(f"experiment: {exp_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
