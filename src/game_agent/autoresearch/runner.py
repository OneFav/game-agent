from __future__ import annotations

import csv
import importlib.util
import itertools
import time
from pathlib import Path
from typing import Any

import numpy as np

from game_agent.autoresearch.metrics import ranking_key
from game_agent.envs.drone_ring_game import DroneRingEnv
from game_agent.utils.fs import ensure_empty_output_dir, read_yaml, write_json, write_yaml
from game_agent.utils.manifest import build_manifest


class AutoResearchRunner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def run(self, scenario_dir: Path, policy_dir: Path, exp_id: str) -> Path:
        scenario_dir = Path(scenario_dir)
        policy_dir = Path(policy_dir)
        exp_dir = self.project_root / "experiments" / exp_id
        ensure_empty_output_dir(exp_dir)

        spec = read_yaml(scenario_dir / "task_spec.yaml")
        default_config = read_yaml(policy_dir / "default_config.yaml")
        search_space = read_yaml(policy_dir / "search_space.yaml")
        evaluation_metrics = spec.get("evaluation_metrics", {})
        seeds = _trial_seeds(spec, search_space)

        rows: list[dict[str, Any]] = []
        for index, config in enumerate(_expand_configs(default_config, search_space), start=1):
            trial_id = f"trial_{index:04d}"
            trial_dir = exp_dir / "trials" / trial_id
            trial_dir.mkdir(parents=True, exist_ok=True)
            config_path = trial_dir / "config.yaml"
            write_yaml(config_path, config)

            started = time.perf_counter()
            metrics = evaluate_policy_config(policy_dir, spec, config, seeds)
            ranking_key(metrics, evaluation_metrics)
            log = {
                "trial_id": trial_id,
                "scenario_id": spec.get("task_id", scenario_dir.name),
                "policy_id": policy_dir.name,
                "seeds": seeds,
                "wall_time_seconds": float(time.perf_counter() - started),
            }
            write_json(trial_dir / "metrics.json", metrics)
            write_json(trial_dir / "log.json", log)

            rows.append({"trial_id": trial_id, "config": config, "metrics": metrics})

        rows.sort(key=lambda item: ranking_key(item["metrics"], evaluation_metrics))
        best = rows[0]
        _write_leaderboard(exp_dir / "leaderboard.csv", rows)
        write_yaml(exp_dir / "best_config.yaml", best["config"])
        (exp_dir / "report.md").write_text(_report(exp_id, best), encoding="utf-8")
        write_json(exp_dir / "manifest.json", build_manifest(exp_dir, "experiment", exp_id))
        return exp_dir


def evaluate_policy_dir(
    policy_dir: Path,
    scenario_dir: Path,
    config_path: Path | None = None,
    seeds: list[int] | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Evaluate a generated policy package from paths.

    Extra keyword arguments are accepted so generated infer.py can call this as
    an optional fallback without coupling to AutoResearch internals.
    """
    policy_dir = Path(policy_dir)
    scenario_dir = Path(scenario_dir)
    spec = read_yaml(scenario_dir / "task_spec.yaml")
    config = read_yaml(Path(config_path) if config_path else policy_dir / "default_config.yaml")
    selected_seeds = seeds or _trial_seeds(spec, {"budget": {"seeds_per_trial": 1}})
    metrics, per_seed_metrics = _evaluate(policy_dir, spec, config, selected_seeds)
    return {
        "schema_version": "1.0",
        "status": "completed",
        "metrics": _nested_metrics(metrics, spec.get("evaluation_metrics", {}), len(selected_seeds)),
        "raw_metrics": metrics,
        "per_seed_metrics": per_seed_metrics,
        "seeds_evaluated": selected_seeds,
        "n_episodes": len(selected_seeds),
    }


def evaluate_policy_config(
    policy_dir: Path,
    spec: dict[str, Any],
    config: dict[str, Any],
    seeds: list[int],
) -> dict[str, float]:
    metrics, _per_seed_metrics = _evaluate(Path(policy_dir), spec, config, seeds)
    return metrics


def _evaluate(
    policy_dir: Path,
    spec: dict[str, Any],
    config: dict[str, Any],
    seeds: list[int],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    PolicyClass = _load_policy_class(policy_dir)
    per_seed_metrics = [_run_episode(PolicyClass, spec, config, int(seed)) for seed in seeds]
    count = max(len(per_seed_metrics), 1)
    metrics = {
        "success_rate": sum(item["success_rate"] for item in per_seed_metrics) / count,
        "collision_rate": sum(item["collision_rate"] for item in per_seed_metrics) / count,
        "out_of_bounds_rate": sum(item["out_of_bounds_rate"] for item in per_seed_metrics) / count,
        "avg_episode_length": sum(item["episode_length"] for item in per_seed_metrics) / count,
        "action_violation_rate": sum(item["action_violation_rate"] for item in per_seed_metrics) / count,
    }
    return metrics, per_seed_metrics


def _run_episode(PolicyClass: type, spec: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]:
    env = DroneRingEnv(spec.get("env_config", {}))
    policy = PolicyClass(config, spec)
    policy.reset(seed)
    observations, info = env.reset(seed=seed)
    latest_metrics = dict(info.get("metrics", {}))
    action_violations = 0
    steps = 0
    max_steps = int(spec.get("env_config", {}).get("max_steps", getattr(env, "max_steps", 200)))

    for _ in range(max_steps):
        actions = {}
        for agent_id in env.agents:
            action = np.asarray(policy.act(observations, agent_id, info), dtype=np.float32)
            if action.shape != env.action_shape:
                action_violations += 1
                action = np.zeros(env.action_shape, dtype=np.float32)
            actions[agent_id] = action
        observations, _rewards, terminated, truncated, info = env.step(actions)
        latest_metrics = dict(info.get("metrics", {}))
        steps += 1
        if all(terminated.values()) or all(truncated.values()):
            break

    return {
        "seed": seed,
        "success": bool(latest_metrics.get("success", False)),
        "collision": bool(latest_metrics.get("collision", False)),
        "out_of_bounds": bool(latest_metrics.get("out_of_bounds", False)),
        "success_rate": 1.0 if latest_metrics.get("success", False) else 0.0,
        "collision_rate": 1.0 if latest_metrics.get("collision", False) else 0.0,
        "out_of_bounds_rate": 1.0 if latest_metrics.get("out_of_bounds", False) else 0.0,
        "episode_length": int(latest_metrics.get("episode_length", steps)),
        "action_violation_rate": float(action_violations / max(steps * len(env.agents), 1)),
    }


def _load_policy_class(policy_dir: Path) -> type:
    policy_path = policy_dir / "policy.py"
    module_name = f"_game_agent_policy_{abs(hash(policy_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, policy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load policy module: {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _nested_metrics(raw_metrics: dict[str, float], evaluation_metrics: dict[str, Any], episode_count: int) -> dict[str, Any]:
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    primary_direction = str(primary.get("direction", "maximize"))
    if primary_name not in raw_metrics:
        raise KeyError(f"Missing primary metric: {primary_name}")

    return {
        "primary": {
            "name": primary_name,
            "value": float(raw_metrics[primary_name]),
            "direction": primary_direction,
            "mean": float(raw_metrics[primary_name]),
            "std": 0.0,
            "n": int(episode_count),
        },
        "secondary": _secondary_metrics(raw_metrics, evaluation_metrics),
        "hard_constraints": _hard_constraint_metrics(raw_metrics, evaluation_metrics),
    }


def _secondary_metrics(raw_metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> dict[str, Any]:
    secondary: dict[str, Any] = {}
    for item in evaluation_metrics.get("secondary", []):
        source_name = str(item.get("name", ""))
        output_name = "avg_episode_length" if source_name == "episode_length" else source_name
        if output_name in raw_metrics:
            secondary[output_name] = {
                "value": float(raw_metrics[output_name]),
                "mean": float(raw_metrics[output_name]),
                "std": 0.0,
                "direction": str(item.get("direction", "minimize")),
            }
    if "avg_episode_length" not in secondary and "avg_episode_length" in raw_metrics:
        secondary["avg_episode_length"] = {
            "value": float(raw_metrics["avg_episode_length"]),
            "mean": float(raw_metrics["avg_episode_length"]),
            "std": 0.0,
            "direction": "minimize",
        }
    return secondary


def _hard_constraint_metrics(raw_metrics: dict[str, float], evaluation_metrics: dict[str, Any]) -> dict[str, Any]:
    hard_constraints: dict[str, Any] = {}
    for constraint in evaluation_metrics.get("hard_constraints", []):
        name = str(constraint.get("name", ""))
        if not name:
            raise ValueError("Hard constraint must define name")
        if name not in raw_metrics:
            raise KeyError(f"Missing hard constraint metric: {name}")
        value = float(raw_metrics[name])
        entry: dict[str, Any] = {"value": value}
        if "max" in constraint:
            max_value = float(constraint["max"])
            entry["max"] = max_value
            entry["passed"] = value <= max_value
        elif "min" in constraint:
            min_value = float(constraint["min"])
            entry["min"] = min_value
            entry["passed"] = value >= min_value
        else:
            raise ValueError(f"Hard constraint must define max or min: {name}")
        hard_constraints[name] = entry
    return hard_constraints


def _expand_configs(default_config: dict[str, Any], search_space: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = search_space.get("parameters", {})
    names = list(parameters)
    values = [parameters[name].get("values", [default_config.get(name)]) for name in names]
    max_trials = int(search_space.get("budget", {}).get("max_trials", 1))
    configs: list[dict[str, Any]] = []
    for combination in itertools.product(*values):
        config = dict(default_config)
        config.update(dict(zip(names, combination)))
        configs.append(config)
        if len(configs) >= max_trials:
            break
    return configs


def _trial_seeds(spec: dict[str, Any], search_space: dict[str, Any]) -> list[int]:
    splits = spec.get("splits", {})
    seeds = splits.get("val_seeds") or splits.get("validation", {}).get("seeds") or splits.get("eval", {}).get("seeds")
    if not seeds:
        seeds = [0, 1, 2]
    limit = int(search_space.get("budget", {}).get("seeds_per_trial", len(seeds)))
    return [int(seed) for seed in list(seeds)[:limit]]


def _write_leaderboard(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "rank",
        "trial_id",
        "success_rate",
        "collision_rate",
        "out_of_bounds_rate",
        "avg_episode_length",
        "action_violation_rate",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            metrics = row["metrics"]
            writer.writerow({"rank": rank, "trial_id": row["trial_id"], **{name: metrics.get(name, "") for name in fieldnames[2:]}})


def _report(exp_id: str, best: dict[str, Any]) -> str:
    metrics = best["metrics"]
    return (
        f"# AutoResearch Report: {exp_id}\n\n"
        f"- Best trial: `{best['trial_id']}`\n"
        f"- success_rate: {metrics['success_rate']:.3f}\n"
        f"- collision_rate: {metrics['collision_rate']:.3f}\n"
        f"- avg_episode_length: {metrics['avg_episode_length']:.3f}\n"
    )
