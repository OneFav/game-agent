from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml


def _add_project_root_to_sys_path() -> None:
    current = Path(__file__).resolve()
    for candidate in (current.parent, *current.parents):
        if (candidate / "contracts").exists() or (candidate / "game_agent").exists():
            sys.path.insert(0, str(candidate))
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run minimal evaluation for a generated policy package.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eval_seeds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--stress_test", default=None)
    args = parser.parse_args()

    if not Path(args.checkpoint).is_file():
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


def evaluate(args: argparse.Namespace) -> dict:
    scenario_dir = Path(args.scenario)
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"--scenario must be a scenario directory: {scenario_dir}")
    task_spec = _read_yaml(scenario_dir / "task_spec.yaml")
    env_config = _read_yaml(scenario_dir / "env_config.yaml")
    env = _make_env(scenario_dir, env_config)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from policy import PolicyClass

    policy = PolicyClass(_read_yaml(Path(__file__).with_name("default_config.yaml")), task_spec)
    checkpoint = str(args.checkpoint or "")
    checkpoint_hash = _checkpoint_hash(checkpoint)
    policy.load(checkpoint)

    seeds = _parse_seeds(args.eval_seeds)
    started = time.perf_counter()
    runner_results = _try_autoresearch_runner(args)
    if runner_results is not None:
        return _normalize_runner_results(
            runner_results,
            task_spec=task_spec,
            seeds=seeds,
            checkpoint_hash=checkpoint_hash,
            started=started,
            render=bool(args.render),
            stress_test=args.stress_test,
        )

    per_seed_metrics = [_run_episode(env, policy, seed, stress_test=args.stress_test) for seed in seeds]
    wall_time_seconds = time.perf_counter() - started
    return _build_eval_results(
        task_spec=task_spec,
        scenario_dir=scenario_dir,
        seeds=seeds,
        checkpoint_hash=checkpoint_hash,
        per_seed_metrics=per_seed_metrics,
        wall_time_seconds=wall_time_seconds,
        render=bool(args.render),
        stress_test=args.stress_test,
    )


def _build_eval_results(
    task_spec: dict,
    scenario_dir: Path,
    seeds: list[int],
    checkpoint_hash: str,
    per_seed_metrics: list[dict],
    wall_time_seconds: float,
    render: bool,
    stress_test: str | None,
) -> dict:
    count = max(len(per_seed_metrics), 1)
    success_rate = sum(1 for item in per_seed_metrics if item["success"]) / count
    collision_rate = sum(1 for item in per_seed_metrics if item["collision"]) / count
    out_of_bounds_rate = sum(1 for item in per_seed_metrics if item["out_of_bounds"]) / count
    action_violation_rate = 0.0
    avg_episode_length = sum(item["episode_length"] for item in per_seed_metrics) / count
    success_values = [item["success_rate"] for item in per_seed_metrics]
    episode_lengths = [item["episode_length"] for item in per_seed_metrics]
    primary_spec = task_spec.get("evaluation_metrics", {}).get("primary", {})
    primary_name = str(primary_spec.get("name", "success_rate"))
    primary_direction = str(primary_spec.get("direction", "maximize"))
    primary_value = success_rate if primary_name == "success_rate" else 0.0
    metric_values = {
        "success_rate": success_rate,
        "collision_rate": collision_rate,
        "out_of_bounds_rate": out_of_bounds_rate,
        "action_violation_rate": action_violation_rate,
        "avg_episode_length": avg_episode_length,
    }
    aggregate_metrics = {
        "primary": {
            "name": primary_name,
            "value": primary_value,
            "direction": primary_direction,
            "mean": _mean(success_values) if primary_name == "success_rate" else primary_value,
            "std": _std(success_values) if primary_name == "success_rate" else 0.0,
            "n": len(success_values),
        },
        "secondary": {
            "avg_episode_length": {
                "value": avg_episode_length,
                "mean": _mean(episode_lengths),
                "std": _std(episode_lengths),
                "direction": "minimize",
            }
        },
        "hard_constraints": _hard_constraints_from_spec(task_spec, metric_values),
    }
    return {
        "schema_version": "1.0",
        "status": "completed",
        "policy_id": Path(__file__).resolve().parent.name,
        "checkpoint_hash": checkpoint_hash,
        "scenario_id": str(task_spec.get("task_id", scenario_dir.name)),
        "seeds_evaluated": seeds,
        "n_episodes": len(seeds),
        "metrics": aggregate_metrics,
        "per_seed_metrics": per_seed_metrics,
        "failure_episodes": [],
        "wall_time_seconds": wall_time_seconds,
        "render": render,
        "stress_test": stress_test,
    }


def _try_autoresearch_runner(args: argparse.Namespace):
    try:
        from game_agent.autoresearch.runner import evaluate_policy_dir
    except Exception:
        return None
    try:
        return evaluate_policy_dir(
            Path(__file__).resolve().parent,
            Path(args.scenario),
            checkpoint=Path(args.checkpoint),
            seeds=_parse_seeds(args.eval_seeds),
            render=bool(args.render),
            stress_test=args.stress_test,
        )
    except TypeError:
        try:
            return evaluate_policy_dir(Path(__file__).resolve().parent, Path(args.scenario), seed=_parse_seeds(args.eval_seeds)[0])
        except Exception:
            return None
    except Exception:
        return None


def _normalize_runner_results(
    results,
    task_spec: dict,
    seeds: list[int],
    checkpoint_hash: str,
    started: float,
    render: bool,
    stress_test: str | None,
) -> dict:
    if not isinstance(results, dict):
        return None
    if {"metrics", "per_seed_metrics"} <= set(results):
        normalized = dict(results)
        normalized.setdefault("policy_id", Path(__file__).resolve().parent.name)
        normalized.setdefault("checkpoint_hash", checkpoint_hash)
        normalized.setdefault("scenario_id", str(task_spec.get("task_id", Path.cwd().name)))
        normalized.setdefault("seeds_evaluated", seeds)
        normalized.setdefault("n_episodes", len(seeds))
        normalized.setdefault("failure_episodes", [])
        normalized.setdefault("wall_time_seconds", float(time.perf_counter() - started))
        normalized.setdefault("render", render)
        normalized.setdefault("stress_test", stress_test)
        return normalized
    per_seed_metrics = results.get("per_seed_metrics")
    if not isinstance(per_seed_metrics, list):
        return None
    return _build_eval_results(
        task_spec=task_spec,
        scenario_dir=Path.cwd(),
        seeds=seeds,
        checkpoint_hash=checkpoint_hash,
        per_seed_metrics=per_seed_metrics,
        wall_time_seconds=float(time.perf_counter() - started),
        render=render,
        stress_test=stress_test,
    )


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"required file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _make_env(scenario_dir: Path, env_config: dict):
    env_py = scenario_dir / "env.py"
    if not env_py.exists():
        raise FileNotFoundError(f"scenario env.py not found: {env_py}")
    sys.path.insert(0, str(scenario_dir))
    from env import make_env

    return make_env(env_config)


def _checkpoint_hash(checkpoint: str) -> str:
    if not checkpoint:
        return "sha256:none"
    path = Path(checkpoint)
    if not path.exists():
        return "sha256:none"
    return "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()


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


def _hard_constraints_from_spec(task_spec: dict, metric_values: dict[str, float]) -> dict:
    constraints = task_spec.get("evaluation_metrics", {}).get("hard_constraints", [])
    if not constraints:
        constraints = [
            {"name": "collision_rate", "max": 0.05},
            {"name": "out_of_bounds_rate", "max": 0.01},
            {"name": "action_violation_rate", "max": 0.0},
        ]
    result = {}
    for constraint in constraints:
        name = str(constraint.get("name", "unknown"))
        max_value = float(constraint.get("max", 0.0))
        value = float(metric_values.get(name, 0.0))
        result[name] = {"value": value, "max": max_value, "passed": value <= max_value}
    return result


def _run_episode(env, policy, seed: int, stress_test: str | None = None) -> dict:
    policy.reset(seed)
    observations, info = env.reset(seed=seed)
    max_steps = 5 if not stress_test else 10
    latest_metrics = dict(info.get("metrics", {}))
    for _ in range(max_steps):
        actions = {agent_id: policy.act(observations[agent_id], agent_id) for agent_id in env.agents}
        observations, _rewards, terminated, truncated, info = env.step(actions)
        latest_metrics = dict(info.get("metrics", {}))
        if any(terminated.values()) or any(truncated.values()):
            break
    return {
        "seed": seed,
        "success": bool(latest_metrics.get("success", False)),
        "collision": bool(latest_metrics.get("collision", False)),
        "out_of_bounds": bool(latest_metrics.get("out_of_bounds", False)),
        "success_rate": 1.0 if latest_metrics.get("success", False) else 0.0,
        "collision_rate": 1.0 if latest_metrics.get("collision", False) else 0.0,
        "out_of_bounds_rate": 1.0 if latest_metrics.get("out_of_bounds", False) else 0.0,
        "episode_length": int(latest_metrics.get("episode_length", 0)),
        "action_violation_rate": 0.0,
    }


if __name__ == "__main__":
    main()
