from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def _add_project_root_to_sys_path() -> None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "contracts").exists() or (candidate / "src" / "contracts").exists():
            sys.path.insert(0, str(candidate))
            src_path = candidate / "src"
            if src_path.exists():
                sys.path.insert(0, str(src_path))
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the lossy 3-ring rule policy.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eval_seeds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--stress_test", default=None)
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.is_file():
        print(f"error: checkpoint does not exist: {args.checkpoint}", file=sys.stderr)
        raise SystemExit(3)

    _add_project_root_to_sys_path()
    try:
        results = evaluate(args)
    except Exception as error:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        failure = {"status": "failed", "error": str(error), "seeds": _parse_seeds(args.eval_seeds)}
        output.write_text(json.dumps(failure, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        raise SystemExit(2) from error

    Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    scenario_dir = Path(args.scenario)
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"--scenario must be a scenario directory: {scenario_dir}")

    task_spec = _read_yaml(scenario_dir / "task_spec.yaml")
    env_config = _read_yaml(scenario_dir / "env_config.yaml")
    checkpoint_payload = _read_checkpoint(Path(args.checkpoint))
    config = checkpoint_payload.get("config") if isinstance(checkpoint_payload.get("config"), dict) else {}
    if not config:
        config = _read_yaml(Path(__file__).with_name("default_config.yaml"))

    env = _make_env(scenario_dir, env_config)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from policy import PolicyClass

    policy = PolicyClass(config, task_spec)
    policy.load(args.checkpoint)
    seeds = _parse_seeds(args.eval_seeds)
    started = time.perf_counter()
    per_seed_metrics = [_run_episode(env, policy, seed) for seed in seeds]
    wall_time_seconds = float(time.perf_counter() - started)
    metric_values = _aggregate_metrics(per_seed_metrics)
    return {
        "schema_version": "1.0",
        "status": "completed",
        "policy_id": Path(__file__).resolve().parent.name,
        "checkpoint_hash": _checkpoint_hash(args.checkpoint),
        "scenario_id": str(task_spec.get("task_id", scenario_dir.name)),
        "seeds_evaluated": seeds,
        "n_episodes": len(seeds),
        "metrics": _format_metrics(task_spec, metric_values, per_seed_metrics),
        "per_seed_metrics": per_seed_metrics,
        "failure_episodes": [item["seed"] for item in per_seed_metrics if item["collision"] or item["out_of_bounds"]],
        "wall_time_seconds": wall_time_seconds,
        "render": bool(args.render),
        "stress_test": args.stress_test,
    }


def _run_episode(env: Any, policy: Any, seed: int) -> dict[str, Any]:
    policy.reset(seed)
    observations, info = env.reset(seed=seed)
    latest_metrics = dict(info.get("metrics", {}))
    action_violations = 0
    communication_drop_events = int(info.get("communication_dropped", {}).get("drop_events", 0))

    for _ in range(int(getattr(env, "max_steps", 200))):
        actions: dict[str, np.ndarray] = {}
        for agent_id in env.agents:
            action = np.asarray(policy.act(observations, agent_id, info), dtype=np.float32)
            if action.shape != getattr(env, "action_shape", (4,)):
                action_violations += 1
                action = np.zeros(getattr(env, "action_shape", (4,)), dtype=np.float32)
            actions[agent_id] = action

        observations, _rewards, terminated, truncated, info = env.step(actions)
        latest_metrics = dict(info.get("metrics", {}))
        communication_drop_events += int(info.get("communication_dropped", {}).get("drop_events", 0))
        if all(terminated.values()) or all(truncated.values()):
            break

    return {
        "seed": seed,
        "success": bool(latest_metrics.get("success", False)),
        "collision": bool(latest_metrics.get("collision", False)),
        "out_of_bounds": bool(latest_metrics.get("out_of_bounds", False)),
        "timeout": bool(latest_metrics.get("timeout", False)),
        "success_rate": 1.0 if latest_metrics.get("success", False) else 0.0,
        "collision_rate": 1.0 if latest_metrics.get("collision", False) else 0.0,
        "out_of_bounds_rate": 1.0 if latest_metrics.get("out_of_bounds", False) else 0.0,
        "timeout_rate": 1.0 if latest_metrics.get("timeout", False) else 0.0,
        "episode_length": int(latest_metrics.get("episode_length", 0)),
        "action_violation_rate": float(action_violations / max(int(latest_metrics.get("episode_length", 1)) * len(env.agents), 1)),
        "ring_passed_count": int(latest_metrics.get("ring_passed_count", 0)),
        "communication_drop_events": communication_drop_events,
    }


def _aggregate_metrics(per_seed_metrics: list[dict[str, Any]]) -> dict[str, float]:
    count = max(len(per_seed_metrics), 1)
    return {
        "success_rate": sum(item["success_rate"] for item in per_seed_metrics) / count,
        "collision_rate": sum(item["collision_rate"] for item in per_seed_metrics) / count,
        "out_of_bounds_rate": sum(item["out_of_bounds_rate"] for item in per_seed_metrics) / count,
        "timeout_rate": sum(item["timeout_rate"] for item in per_seed_metrics) / count,
        "avg_episode_length": sum(item["episode_length"] for item in per_seed_metrics) / count,
        "action_violation_rate": sum(item["action_violation_rate"] for item in per_seed_metrics) / count,
    }


def _format_metrics(
    task_spec: dict[str, Any],
    metric_values: dict[str, float],
    per_seed_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    primary_spec = task_spec.get("evaluation_metrics", {}).get("primary", {})
    primary_name = str(primary_spec.get("name", "success_rate"))
    primary_direction = str(primary_spec.get("direction", "maximize"))
    primary_samples = [float(item.get(primary_name, 0.0)) for item in per_seed_metrics]

    secondary = {}
    for item in task_spec.get("evaluation_metrics", {}).get("secondary", []):
        name = str(item.get("name", ""))
        output_name = "avg_episode_length" if name == "episode_length" else name
        if output_name in metric_values:
            secondary[output_name] = {
                "value": float(metric_values[output_name]),
                "mean": float(metric_values[output_name]),
                "std": _std([float(seed_item.get(output_name, seed_item.get(name, 0.0))) for seed_item in per_seed_metrics]),
                "direction": str(item.get("direction", "minimize")),
            }

    return {
        "primary": {
            "name": primary_name,
            "value": float(metric_values.get(primary_name, 0.0)),
            "direction": primary_direction,
            "mean": _mean(primary_samples),
            "std": _std(primary_samples),
            "n": len(primary_samples),
        },
        "secondary": secondary,
        "hard_constraints": _hard_constraints_from_spec(task_spec, metric_values),
    }


def _hard_constraints_from_spec(task_spec: dict[str, Any], metric_values: dict[str, float]) -> dict[str, Any]:
    constraints = task_spec.get("evaluation_metrics", {}).get("hard_constraints", [])
    result: dict[str, Any] = {}
    for constraint in constraints:
        name = str(constraint.get("name", "unknown"))
        max_value = float(constraint.get("max", 0.0))
        value = float(metric_values.get(name, 0.0))
        result[name] = {"value": value, "max": max_value, "passed": value <= max_value}
    return result


def _make_env(scenario_dir: Path, env_config: dict[str, Any]) -> Any:
    env_py = scenario_dir / "env.py"
    if not env_py.exists():
        raise FileNotFoundError(f"scenario env.py not found: {env_py}")
    sys.path.insert(0, str(scenario_dir))
    from env import make_env

    return make_env(env_config)


def _read_checkpoint(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _checkpoint_hash(checkpoint: str) -> str:
    path = Path(checkpoint)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_seeds(value: str) -> list[int]:
    seeds = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not seeds:
        raise ValueError("--eval_seeds must contain at least one integer seed")
    return seeds


def _mean(values: list[float]) -> float:
    return float(sum(values) / max(len(values), 1))


def _std(values: list[float]) -> float:
    mean = _mean(values)
    return float((sum((value - mean) ** 2 for value in values) / max(len(values), 1)) ** 0.5)


if __name__ == "__main__":
    main()
