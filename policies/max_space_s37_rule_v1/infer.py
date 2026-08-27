from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml


EXPECTED_SCENARIO_ID = 'S37'


def main(argv: list[str] | None = None) -> int:
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
        _add_source_root()
        from game_agent.scenarios import catalog_by_id, create_runtime

        scenario_spec = _scenario_spec(scenario_path, catalog_by_id())
        PolicyClass = _load_policy_class()
        config = _read_yaml(Path(__file__).with_name("default_config.yaml"))
        seeds = _parse_seeds(args.eval_seeds)
        per_seed = []
        started = time.perf_counter()
        for seed in seeds:
            runtime = create_runtime(scenario_spec)
            descriptor = runtime.describe()
            env_spec = dict(scenario_spec)
            env_spec["action_space"] = dict(descriptor.action_spaces[descriptor.agents[0]])
            policy = PolicyClass(config, env_spec)
            policy.load(str(checkpoint))
            policy.reset(seed)
            observations, info = runtime.reset(seed=seed)
            for _ in range(int(getattr(runtime, "max_steps", 200))):
                actions = {agent: policy.act(observations, agent, info) for agent in runtime.agents}
                observations, _rewards, terminated, truncated, info = runtime.step(actions)
                if all(terminated.values()) or all(truncated.values()):
                    break
            metrics = runtime.get_metrics()
            per_seed.append({
                "seed": seed,
                "primary_value": float(metrics.get("primary_value", 0.0)),
                "success_rate": float(metrics.get("success_rate", 0.0)),
                "collision_rate": float(metrics.get("collision_rate", 0.0)),
                "out_of_bounds_rate": float(metrics.get("out_of_bounds_rate", 0.0)),
                "action_violation_rate": float(metrics.get("action_violation_rate", 0.0)),
                "episode_length": int(metrics.get("episode_length", 0)),
            })
            runtime.close()
        primary_values = [item["primary_value"] for item in per_seed]
        hard_constraints = {}
        for name in ("collision_rate", "out_of_bounds_rate", "action_violation_rate"):
            value = float(np.mean([item[name] for item in per_seed]))
            hard_constraints[name] = {"value": value, "max": 0.0, "passed": value <= 0.0}
        output_data = {
            "schema_version": "1.0",
            "status": "completed",
            "policy_id": Path(__file__).resolve().parent.name,
            "scenario_id": scenario_spec["scenario_id"],
            "metrics": {
                "primary": {
                    "name": scenario_spec["primary_metric"],
                    "value": float(np.mean(primary_values)),
                    "mean": float(np.mean(primary_values)),
                    "std": float(np.std(primary_values)),
                    "n": len(primary_values),
                },
                "secondary": {
                    "success_rate": {"value": float(np.mean([item["success_rate"] for item in per_seed]))},
                    "avg_episode_length": {"value": float(np.mean([item["episode_length"] for item in per_seed]))},
                },
                "hard_constraints": hard_constraints,
            },
            "per_seed_metrics": per_seed,
            "failure_episodes": [
                {"seed": item["seed"], "failure_type": "task_incomplete"}
                for item in per_seed if item["success_rate"] < 1.0
            ],
            "wall_time_seconds": float(time.perf_counter() - started),
            "render": bool(args.render),
            "stress_test": args.stress_test,
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(output_data, indent=2) + "\n", encoding="utf-8")
        return 0
    except MemoryError:
        return 3
    except Exception as error:
        print(f"inference error: {error}", file=sys.stderr)
        return 1


def _scenario_spec(path: Path, catalog: dict) -> dict:
    candidate = path / "task_spec.yaml" if path.is_dir() else path
    if candidate.is_file():
        loaded = _read_yaml(candidate)
        if loaded.get("runtime_config"):
            return loaded
    if EXPECTED_SCENARIO_ID == "ALL":
        raise ValueError("zero baseline inference needs one representative scenario spec")
    return catalog[EXPECTED_SCENARIO_ID]


def _load_policy_class() -> type:
    path = Path(__file__).with_name("policy.py")
    spec = importlib.util.spec_from_file_location("_max_space_infer_policy", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PolicyClass


def _add_source_root() -> None:
    for parent in Path(__file__).resolve().parents:
        source_root = parent / "src"
        if (source_root / "game_agent").is_dir():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


def _read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def _parse_seeds(raw: str) -> list[int]:
    stripped = raw.strip()
    values = json.loads(stripped) if stripped.startswith("[") else stripped.split(",")
    seeds = [int(value) for value in values if str(value).strip()]
    if not seeds:
        raise ValueError("--eval_seeds must contain at least one integer")
    return seeds


if __name__ == "__main__":
    raise SystemExit(main())
