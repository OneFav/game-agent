from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the vertical_wave_3v3 rule policy.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eval_seeds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--stress_test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        scenario_dir = Path(args.scenario).resolve()
        if not scenario_dir.is_dir():
            return 1
        policy = _load_policy_class()(_load_checkpoint_config(Path(args.checkpoint)), _load_task_spec(scenario_dir))
        env_module = _load_env_module(scenario_dir)
        seeds = _parse_seeds(args.eval_seeds)
        per_seed = [_run_episode(env_module, policy, seed) for seed in seeds]
        results = _summarize(per_seed, seeds)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"inference failed: {error}", file=sys.stderr)
        return 1


def _load_policy_class() -> type:
    policy_path = Path(__file__).with_name("policy.py")
    spec = importlib.util.spec_from_file_location("_vertical_wave_policy", policy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load policy.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_vertical_wave_policy"] = module
    spec.loader.exec_module(module)
    return module.PolicyClass


def _load_env_module(scenario_dir: Path) -> Any:
    env_path = scenario_dir / "env.py"
    spec = importlib.util.spec_from_file_location("_vertical_wave_env", env_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scenario env.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_vertical_wave_env"] = module
    spec.loader.exec_module(module)
    return module


def _load_task_spec(scenario_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((scenario_dir / "task_spec.yaml").read_text(encoding="utf-8")) or {}


def _load_checkpoint_config(checkpoint_path: Path) -> dict[str, Any]:
    if checkpoint_path.is_file():
        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict) and isinstance(data.get("config"), dict):
            return data["config"]
    default_path = Path(__file__).with_name("default_config.yaml")
    return yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}


def _parse_seeds(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _run_episode(env_module: Any, policy: Any, seed: int) -> dict[str, Any]:
    env = env_module.make_env()
    policy.reset(seed)
    _observations, infos = env.reset(seed=seed)
    action_violations = 0

    for _ in range(1, int(getattr(env, "max_steps", 800)) + 1):
        actions = policy.compute_actions(env)
        for agent_id, action in actions.items():
            action_array = np.asarray(action, dtype=np.float32)
            if action_array.shape != tuple(env.action_shape):
                action_violations += 1
                actions[agent_id] = np.zeros(env.action_shape, dtype=np.float32)
                continue
            if np.any(action_array < env._action_low) or np.any(action_array > env._action_high):
                action_violations += 1
        _observations, _rewards, terminations, truncations, infos = env.step(actions)
        if all(terminations.values()) or all(truncations.values()):
            break

    red_info = infos["red_racer_0"]
    blue_info = infos["blue_racer_0"]
    team_score = float(red_info.get("team_score", 0.0))
    blue_team_score = float(blue_info.get("team_score", 0.0))
    collision = any(bool(info.get("collision", False)) for info in infos.values())
    out_of_bounds = any(bool(info.get("out_of_bounds", False)) for info in infos.values())
    steps = int(env.base_env.step_count)
    denom = max(steps * len(getattr(env, "agents", [])), 1)
    return {
        "seed": seed,
        "red_score": team_score,
        "blue_score": blue_team_score,
        "team_score": team_score,
        "blue_team_score": blue_team_score,
        "advantage_score": blue_team_score - team_score,
        "score_margin": team_score - blue_team_score,
        "collision": collision,
        "out_of_bounds": out_of_bounds,
        "collision_rate": 1.0 if collision else 0.0,
        "out_of_bounds_rate": 1.0 if out_of_bounds else 0.0,
        "episode_length": steps,
        "action_violation_rate": float(action_violations / denom),
    }


def _summarize(per_seed: list[dict[str, Any]], seeds: list[int]) -> dict[str, Any]:
    count = max(len(per_seed), 1)
    team_scores = [float(item["team_score"]) for item in per_seed]
    blue_scores = [float(item["blue_team_score"]) for item in per_seed]
    advantage_scores = [float(item["advantage_score"]) for item in per_seed]
    score_margins = [float(item["score_margin"]) for item in per_seed]
    collision_rate = sum(float(item["collision_rate"]) for item in per_seed) / count
    out_of_bounds_rate = sum(float(item["out_of_bounds_rate"]) for item in per_seed) / count
    action_violation_rate = sum(float(item["action_violation_rate"]) for item in per_seed) / count
    avg_episode_length = sum(float(item["episode_length"]) for item in per_seed) / count
    team_score = sum(team_scores) / count
    blue_team_score = sum(blue_scores) / count
    score_margin = sum(score_margins) / count
    advantage_score = blue_team_score - team_score
    return {
        "metrics": {
            "primary": {
                "name": "blue_advantage",
                "value": advantage_score,
                "std": float(np.std(advantage_scores)) if advantage_scores else 0.0,
                "n": len(seeds),
            },
            "secondary": {
                "red_score": {"value": team_score},
                "blue_score": {"value": blue_team_score},
                "advantage_score": {"value": advantage_score},
                "score_margin": {"value": score_margin},
                "blue_team_score": {"value": blue_team_score},
                "avg_episode_length": {"value": avg_episode_length},
            },
            "hard_constraints": {
                "collision_rate": {"value": collision_rate, "max": 0.05, "passed": collision_rate <= 0.05},
                "out_of_bounds_rate": {"value": out_of_bounds_rate, "max": 0.01, "passed": out_of_bounds_rate <= 0.01},
                "action_violation_rate": {"value": action_violation_rate, "max": 0.0, "passed": action_violation_rate <= 0.0},
            },
        },
        "per_seed_metrics": per_seed,
        "failure_episodes": [
            {"seed": item["seed"], "failure_type": _failure_type(item)}
            for item in per_seed
            if item["advantage_score"] <= 0.0 or item["collision"] or item["out_of_bounds"]
        ],
    }


def _failure_type(item: dict[str, Any]) -> str:
    if item["collision"]:
        return "collision"
    if item["out_of_bounds"]:
        return "out_of_bounds"
    if item["advantage_score"] <= 0.0:
        return "insufficient_blue_advantage"
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
