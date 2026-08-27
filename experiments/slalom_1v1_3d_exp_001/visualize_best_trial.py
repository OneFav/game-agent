from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "scenarios" / "slalom_1v1_3d_001"
POLICY_DIR = ROOT / "policies" / "slalom_1v1_3d_rule_v1"
EXP_DIR = ROOT / "experiments" / "slalom_1v1_3d_exp_001"
OUTPUT_PATH = ROOT / "output" / "example_04_slalom_1v1_3d.png"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from game_agent.envs.swarm_combat.visualizer import save_trajectory_figure

    env_module = _load_module(SCENARIO_DIR / "env.py", "_slalom_1v1_3d_env")
    policy_module = _load_module(POLICY_DIR / "policy.py", "_slalom_1v1_3d_policy")
    best_config = yaml.safe_load((EXP_DIR / "best_config.yaml").read_text(encoding="utf-8")) or {}

    env = env_module.make_env()
    policy = policy_module.PolicyClass(best_config, yaml.safe_load((SCENARIO_DIR / "task_spec.yaml").read_text(encoding="utf-8")) or {})
    observations, infos = env.reset(seed=100)
    policy.reset(100)

    for _ in range(env.max_steps):
        actions = {
            agent_id: np.asarray(policy.act(observations, agent_id, infos.get(agent_id, {})), dtype=np.float32)
            for agent_id in env.agents
        }
        observations, _rewards, terminations, truncations, infos = env.step(actions)
        if all(terminations.values()) or all(truncations.values()):
            break

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_trajectory_figure(env.native_env, str(OUTPUT_PATH), title="Example 4: slalom_1v1_3d best trial trajectory")
    print(OUTPUT_PATH)
    return 0


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
