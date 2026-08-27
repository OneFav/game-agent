from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "scenarios" / "figure_eight_4v4_001"
POLICY_DIR = ROOT / "policies" / "figure_eight_4v4_rule_v1"
EXP_DIR = ROOT / "experiments" / "figure_eight_4v4_exp_001"
OUTPUT_PATH = ROOT / "output" / "example_07_figure_eight_4v4.png"


def main() -> int:
    task_spec = yaml.safe_load((SCENARIO_DIR / "task_spec.yaml").read_text(encoding="utf-8")) or {}
    config = yaml.safe_load((EXP_DIR / "best_config.yaml").read_text(encoding="utf-8")) or {}
    env_module = _load_module(SCENARIO_DIR / "env.py", "_figure_eight_env")
    policy_module = _load_module(POLICY_DIR / "policy.py", "_figure_eight_policy")

    env = env_module.make_env()
    policy = policy_module.PolicyClass(config, task_spec)
    observations, infos = env.reset(seed=100)
    policy.reset(100)

    for _ in range(env.max_steps):
        actions = policy.compute_actions(env)
        observations, _rewards, terminations, truncations, infos = env.step(actions)
        if all(terminations.values()) or all(truncations.values()):
            break

    from game_agent.envs.swarm_combat.visualizer import save_trajectory_figure

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_trajectory_figure(env.base_env, str(OUTPUT_PATH), title="Example 07: figure_eight_4v4 best trial")
    print(OUTPUT_PATH)
    return 0


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
