from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml


def main(package_dir: Path, package_spec: Mapping[str, Any], argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate an explicit max-space rule policy.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--eval_seeds", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--stress_test")
    args = parser.parse_args(argv)
    try:
        checkpoint = Path(args.checkpoint)
        scenario_path = Path(args.scenario)
        if not checkpoint.is_file() or not scenario_path.exists():
            raise ValueError("--checkpoint and --scenario must exist")
        seeds = _parse_seeds(args.eval_seeds)
        spec = _load_scenario_spec(scenario_path, str(package_spec["scenario_id"]))
        results = _evaluate(package_dir, package_spec, spec, checkpoint, seeds)
        results["render"] = bool(args.render)
        results["stress_test"] = args.stress_test
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"inference error: {error}", file=sys.stderr)
        return 1


def _evaluate(
    package_dir: Path,
    package_spec: Mapping[str, Any],
    spec: dict[str, Any],
    checkpoint: Path,
    seeds: list[int],
) -> dict[str, Any]:
    _add_source_root(package_dir)
    from game_agent.scenarios import create_runtime

    PolicyClass = _load_policy_class(package_dir)
    per_seed: list[dict[str, Any]] = []
    started = time.perf_counter()
    for seed in seeds:
        runtime = create_runtime(spec)
        descriptor = runtime.describe()
        action_space = dict(descriptor.action_spaces[descriptor.agents[0]])
        env_spec = dict(spec)
        env_spec["action_space"] = action_space
        policy = PolicyClass(_read_yaml(package_dir / "default_config.yaml"), env_spec)
        policy.load(str(checkpoint))
        policy.reset(seed)
        observations, info = runtime.reset(seed=seed)
        steps = 0
        for _ in range(int(getattr(runtime, "max_steps", 200))):
            actions = {
                agent_id: policy.act(observations, agent_id, info)
                for agent_id in runtime.agents
            }
            observations, _rewards, terminated, truncated, info = runtime.step(actions)
            steps += 1
            if all(terminated.values()) or all(truncated.values()):
                break
        metrics = dict(runtime.get_metrics())
        per_seed.append(
            {
                "seed": seed,
                "primary_value": float(metrics.get("primary_value", 0.0)),
                "success_rate": float(metrics.get("success_rate", 0.0)),
                "collision_rate": float(metrics.get("collision_rate", 0.0)),
                "out_of_bounds_rate": float(metrics.get("out_of_bounds_rate", 0.0)),
                "action_violation_rate": float(metrics.get("action_violation_rate", 0.0)),
                "episode_length": int(metrics.get("episode_length", steps)),
            }
        )
        runtime.close()
    primary_name = str(spec.get("primary_metric", package_spec.get("primary_metric", "primary_value")))
    primary_values = [item["primary_value"] for item in per_seed]
    hard = {}
    for name in ("collision_rate", "out_of_bounds_rate", "action_violation_rate"):
        value = float(np.mean([item[name] for item in per_seed]))
        hard[name] = {"value": value, "max": 0.0, "passed": value <= 0.0}
    return {
        "schema_version": "1.0",
        "status": "completed",
        "policy_id": str(package_spec["policy_id"]),
        "scenario_id": str(spec.get("scenario_id", package_spec["scenario_id"])),
        "seeds_evaluated": seeds,
        "metrics": {
            "primary": {
                "name": primary_name,
                "value": float(np.mean(primary_values)),
                "mean": float(np.mean(primary_values)),
                "std": float(np.std(primary_values)),
                "n": len(primary_values),
            },
            "secondary": {
                "success_rate": {"value": float(np.mean([item["success_rate"] for item in per_seed]))},
                "avg_episode_length": {"value": float(np.mean([item["episode_length"] for item in per_seed]))},
            },
            "hard_constraints": hard,
        },
        "per_seed_metrics": per_seed,
        "failure_episodes": [
            {"seed": item["seed"], "failure_type": "task_incomplete"}
            for item in per_seed
            if item["success_rate"] < 1.0
        ],
        "wall_time_seconds": float(time.perf_counter() - started),
    }


def _load_scenario_spec(path: Path, expected_scenario_id: str) -> dict[str, Any]:
    if path.is_dir() and (path / "task_spec.yaml").is_file():
        value = _read_yaml(path / "task_spec.yaml")
        if value.get("runtime_config"):
            return value
    elif path.is_file():
        value = _read_yaml(path)
        if value.get("runtime_config"):
            return value
    _add_source_root(Path(__file__).resolve())
    from game_agent.scenarios import catalog_by_id

    if expected_scenario_id == "ALL":
        raise ValueError("the zero baseline requires a representative scenario spec, not a suite path")
    return catalog_by_id()[expected_scenario_id]


def _load_policy_class(package_dir: Path) -> type:
    policy_path = package_dir / "policy.py"
    module_name = f"_max_space_infer_policy_{abs(hash(policy_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, policy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load policy: {policy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _add_source_root(anchor: Path) -> None:
    for parent in anchor.resolve().parents:
        source_root = parent / "src"
        if (source_root / "game_agent").is_dir():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def _parse_seeds(raw: str) -> list[int]:
    stripped = raw.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        seeds = [int(item) for item in parsed]
    else:
        seeds = [int(item.strip()) for item in stripped.split(",") if item.strip()]
    if not seeds:
        raise ValueError("--eval_seeds must contain at least one seed")
    return seeds
