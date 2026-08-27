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
    parser = argparse.ArgumentParser(description="Evaluate the wide_slalom_2v2 swarm rule policy.")
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

        task_spec = _load_task_spec(scenario_dir)
        config = _load_checkpoint_config(Path(args.checkpoint))
        policy = _load_policy_class()(config, task_spec)
        env_module = _load_env_module(scenario_dir)
        seeds = _parse_seeds(args.eval_seeds)
        per_seed = [_run_episode(env_module, policy, seed) for seed in seeds]
        results = _summarize(task_spec, per_seed, seeds)

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"inference failed: {error}", file=sys.stderr)
        return 1


def _load_policy_class() -> type:
    policy_path = Path(__file__).with_name("policy.py")
    spec = importlib.util.spec_from_file_location("_wide_slalom_policy", policy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load policy.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_wide_slalom_policy"] = module
    spec.loader.exec_module(module)
    return module.PolicyClass


def _load_env_module(scenario_dir: Path) -> Any:
    env_path = scenario_dir / "env.py"
    spec = importlib.util.spec_from_file_location("_wide_slalom_env", env_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scenario env.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_wide_slalom_env"] = module
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
    observations, infos = env.reset(seed=seed)
    action_violations = 0
    latest_infos = infos
    steps = 0

    for steps in range(1, int(getattr(env, "max_steps", 600)) + 1):
        actions = {}
        for agent_id in env.agents:
            action = np.asarray(policy.act(observations, agent_id, latest_infos.get(agent_id, {})), dtype=np.float32)
            if action.shape != tuple(env.action_shape):
                action_violations += 1
                action = np.zeros(env.action_shape, dtype=np.float32)
            low = getattr(env, "_action_low", np.full(env.action_shape, -1.0, dtype=np.float32))
            high = getattr(env, "_action_high", np.full(env.action_shape, 1.0, dtype=np.float32))
            if bool(np.any(action < low) or np.any(action > high)):
                action_violations += 1
            actions[agent_id] = action
        observations, _rewards, terminations, truncations, latest_infos = env.step(actions)
        if all(terminations.values()) or all(truncations.values()):
            break

    anchor_info = latest_infos.get("red_racer_0", {})
    team_scores = anchor_info.get("team_scores", {})
    termination = anchor_info.get("termination", {})
    red_score = float(team_scores.get("RED", 0.0))
    blue_score = float(team_scores.get("BLUE", 0.0))
    collision = any(bool(info.get("collision", False)) for info in latest_infos.values())
    out_of_bounds = any(bool(info.get("out_of_bounds", False)) for info in latest_infos.values())
    denom = max(steps * len(getattr(env, "agents", [])), 1)
    return {
        "seed": seed,
        "team_score": red_score,
        "red_score": red_score,
        "blue_score": blue_score,
        "winner": str(termination.get("winner", "UNKNOWN")),
        "termination_reason": str(termination.get("reason", "unknown")),
        "collision": bool(collision),
        "out_of_bounds": bool(out_of_bounds),
        "episode_length": int(steps),
        "action_violation_rate": float(action_violations / denom),
        "red_win": 1.0 if termination.get("winner") == "RED" else 0.0,
        "draw": 1.0 if termination.get("winner") == "DRAW" else 0.0,
    }


def _summarize(task_spec: dict[str, Any], per_seed: list[dict[str, Any]], seeds: list[int]) -> dict[str, Any]:
    count = max(len(per_seed), 1)
    team_scores = [float(item["team_score"]) for item in per_seed]
    raw_metrics = {
        "team_score": sum(team_scores) / count,
        "avg_red_score": sum(float(item["red_score"]) for item in per_seed) / count,
        "avg_blue_score": sum(float(item["blue_score"]) for item in per_seed) / count,
        "avg_episode_length": sum(float(item["episode_length"]) for item in per_seed) / count,
        "red_win_rate": sum(float(item["red_win"]) for item in per_seed) / count,
        "draw_rate": sum(float(item["draw"]) for item in per_seed) / count,
        "collision_rate": sum(1.0 for item in per_seed if item["collision"]) / count,
        "out_of_bounds_rate": sum(1.0 for item in per_seed if item["out_of_bounds"]) / count,
        "action_violation_rate": sum(float(item["action_violation_rate"]) for item in per_seed) / count,
    }
    hard_constraints = _build_hard_constraints(task_spec, raw_metrics)
    feasible = all(entry.get("passed", False) for entry in hard_constraints.values())
    return {
        "metrics": {
            "primary": {
                "name": "team_score",
                "value": raw_metrics["team_score"],
                "std": float(np.std(team_scores)) if team_scores else 0.0,
                "n": len(seeds),
            },
            "secondary": {
                "avg_red_score": {"value": raw_metrics["avg_red_score"]},
                "avg_blue_score": {"value": raw_metrics["avg_blue_score"]},
                "avg_episode_length": {"value": raw_metrics["avg_episode_length"]},
                "red_win_rate": {"value": raw_metrics["red_win_rate"]},
                "draw_rate": {"value": raw_metrics["draw_rate"]},
            },
            "hard_constraints": hard_constraints,
        },
        "raw_metrics": raw_metrics,
        "per_seed_metrics": per_seed,
        "failure_episodes": [
            {
                "seed": item["seed"],
                "reason": item["termination_reason"],
                "winner": item["winner"],
            }
            for item in per_seed
            if item["collision"] or item["out_of_bounds"]
        ],
        "feasible": feasible,
    }


def _build_hard_constraints(task_spec: dict[str, Any], raw_metrics: dict[str, float]) -> dict[str, Any]:
    constraints = task_spec.get("evaluation_metrics", {}).get("hard_constraints", [])
    built: dict[str, Any] = {}
    for constraint in constraints:
        name = str(constraint.get("name", ""))
        max_value = float(constraint.get("max", 0.0))
        value = float(raw_metrics.get(name, 0.0))
        built[name] = {"value": value, "max": max_value, "passed": value <= max_value}
    return built


if __name__ == "__main__":
    raise SystemExit(main())
