from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "scenarios" / "wide_slalom_2v2_001"
POLICY_DIR = ROOT / "policies" / "wide_slalom_2v2_rule_v1"
OUTPUT_DIR = ROOT / "experiments" / "wide_slalom_2v2_exp_001"


AGENT_TO_ID = {
    "red_racer_0": 0,
    "red_defender_0": 1,
    "blue_racer_0": 2,
    "blue_defender_0": 3,
}


@dataclass
class FieldView:
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    z_range: tuple[float, float]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(SCENARIO_DIR))

    from env import make_env
    from game_agent.envs.swarm_combat.entities import Gate
    from game_agent.envs.swarm_combat.visualizer import save_trajectory_figure

    task_spec = yaml.safe_load((SCENARIO_DIR / "task_spec.yaml").read_text(encoding="utf-8")) or {}
    config = yaml.safe_load((OUTPUT_DIR / "best_config.yaml").read_text(encoding="utf-8")) or {}
    policy = _load_policy_class()(config, task_spec)

    env = make_env()
    observations, infos = env.reset(seed=100)
    policy.reset(100)

    history = [_snapshot(env)]
    for _ in range(env.max_steps):
        actions = {agent_id: policy.act(observations, agent_id, infos.get(agent_id, {})) for agent_id in env.agents}
        observations, _rewards, terminations, truncations, infos = env.step(actions)
        history.append(_snapshot(env))
        if all(terminations.values()) or all(truncations.values()):
            break

    viz_env = SimpleNamespace(
        cfg=SimpleNamespace(field=FieldView((-26.0, 26.0), (-26.0, 26.0), (0.0, 8.0))),
        gates=[
            Gate(
                gate_id=index,
                center=np.array([float(gate[0]), float(gate[1]), 4.0], dtype=np.float32),
                normal=np.array([1.0, 0.0, 0.0], dtype=np.float32),
                width=3.0,
                height=3.0,
                cooldown_steps=30,
                pass_direction="team_forward",
            )
            for index, gate in enumerate(env._gates)
        ],
        history=history,
    )

    output = OUTPUT_DIR / "trajectory_3d_seed100.png"
    save_trajectory_figure(viz_env, str(output), title="wide_slalom_2v2 best trial 3D trajectory")
    print(output)
    return 0


def _load_policy_class() -> type:
    policy_path = POLICY_DIR / "policy.py"
    spec = importlib.util.spec_from_file_location("wide_slalom_policy", policy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load policy: {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _snapshot(env: Any) -> dict[str, Any]:
    return {
        "step": int(env._step_count),
        "drones": [_drone_snapshot(env, agent_id) for agent_id in env.agents],
        "gates": [
            {"id": index, "cd_red": 0, "cd_blue": 0, "cd_max": 30}
            for index, _gate in enumerate(env._gates)
        ],
        "scores": {"RED": float(env._next_gate), "BLUE": 0.0},
        "pass_events": [],
        "collision_events": [],
    }


def _drone_snapshot(env: Any, agent_id: str) -> dict[str, Any]:
    state = env._states[agent_id]
    x, y = state.position
    vx, vy = state.velocity
    return {
        "id": AGENT_TO_ID[agent_id],
        "team": "RED" if agent_id.startswith("red") else "BLUE",
        "role": "RACER" if "racer" in agent_id else "DEFENDER",
        "pos": np.array([float(x), float(y), _z_for(agent_id)], dtype=np.float32),
        "vel": np.array([float(vx), float(vy), 0.0], dtype=np.float32),
    }


def _z_for(agent_id: str) -> float:
    if "racer" in agent_id:
        return 4.0
    return 5.0


if __name__ == "__main__":
    raise SystemExit(main())
