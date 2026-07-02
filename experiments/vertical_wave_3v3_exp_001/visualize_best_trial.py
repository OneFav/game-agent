from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "scenarios" / "vertical_wave_3v3_001"
POLICY_DIR = ROOT / "policies" / "vertical_wave_3v3_rule_v1"
EXPERIMENT_DIR = ROOT / "experiments" / "vertical_wave_3v3_exp_001"
OUTPUT_PATH = ROOT / "output" / "example_06_vertical_wave_3v3.png"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))

    from game_agent.envs.swarm_combat.visualizer import save_trajectory_figure

    env_module = _load_module(SCENARIO_DIR / "env.py", "vertical_wave_3v3_env_visual")
    policy_module = _load_module(POLICY_DIR / "policy.py", "vertical_wave_3v3_policy_visual")

    task_spec = yaml.safe_load((SCENARIO_DIR / "task_spec.yaml").read_text(encoding="utf-8")) or {}
    config = yaml.safe_load((EXPERIMENT_DIR / "best_config.yaml").read_text(encoding="utf-8")) or {}
    policy = policy_module.PolicyClass(config, task_spec)

    env = env_module.make_env()
    policy.reset(23)
    env.reset(seed=23)

    for _ in range(env.max_steps):
        actions = policy.compute_actions(env)
        _obs, _rewards, terminated, truncated, _infos = env.step(actions)
        if all(terminated.values()) or all(truncated.values()):
            break

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_trajectory_figure(env.base_env, str(OUTPUT_PATH), title="vertical_wave_3v3 best trial 3D trajectory")
    print(OUTPUT_PATH)
    return 0


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
