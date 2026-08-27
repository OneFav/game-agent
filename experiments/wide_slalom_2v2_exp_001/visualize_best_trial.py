from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SCENARIO_DIR = ROOT / "scenarios" / "wide_slalom_2v2_001"
POLICY_DIR = ROOT / "policies" / "wide_slalom_2v2_rule_v1"
OUTPUT_DIR = ROOT / "experiments" / "wide_slalom_2v2_exp_001"
PUBLIC_OUTPUT = ROOT / "output"


def main() -> int:
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(SCENARIO_DIR))

    from env import make_env
    from game_agent.envs.swarm_combat.visualizer import save_topdown_figure, save_trajectory_figure

    task_spec = yaml.safe_load((SCENARIO_DIR / "task_spec.yaml").read_text(encoding="utf-8")) or {}
    config = yaml.safe_load((OUTPUT_DIR / "best_config.yaml").read_text(encoding="utf-8")) or {}
    policy = _load_policy_class()(config, task_spec)
    env = make_env()

    observations, infos = env.reset(seed=100)
    policy.reset(100)
    while True:
        actions = {agent_id: policy.act(observations, agent_id, infos.get(agent_id, {})) for agent_id in env.agents}
        observations, _rewards, terminations, truncations, infos = env.step(actions)
        if all(terminations.values()) or all(truncations.values()):
            break

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUTPUT.mkdir(parents=True, exist_ok=True)

    trajectory_path = OUTPUT_DIR / "trajectory_3d_seed100.png"
    topdown_path = OUTPUT_DIR / "topdown_seed100.png"
    public_path = PUBLIC_OUTPUT / "example_05_wide_slalom_2v2.png"

    save_trajectory_figure(env.raw_env, str(trajectory_path), title="wide_slalom_2v2 best trial trajectory")
    save_topdown_figure(env.raw_env, str(topdown_path), title="wide_slalom_2v2 top-down rollout")
    save_trajectory_figure(env.raw_env, str(public_path), title="Example 05: wide_slalom_2v2")

    print(trajectory_path)
    print(topdown_path)
    print(public_path)
    return 0


def _load_policy_class() -> type:
    policy_path = POLICY_DIR / "policy.py"
    spec = importlib.util.spec_from_file_location("wide_slalom_policy", policy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load policy: {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


if __name__ == "__main__":
    raise SystemExit(main())
