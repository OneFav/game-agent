from __future__ import annotations

import csv
import hashlib
import importlib.util
import itertools
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from game_agent.autoresearch.escalation import ResearchState
from game_agent.autoresearch.metrics import ranking_key
from game_agent.autoresearch.visualization import generate_training_visualizations
from game_agent.scenarios import create_runtime
from game_agent.utils.fs import (
    ensure_empty_output_dir,
    read_json,
    read_yaml,
    write_json,
    write_yaml,
)
from game_agent.utils.manifest import build_manifest


class AutoResearchRunner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def run(self, scenario_dir: Path, policy_dir: Path, exp_id: str) -> Path:
        scenario_dir = Path(scenario_dir)
        policy_dir = Path(policy_dir)
        exp_dir = self.project_root / "experiments" / exp_id
        ensure_empty_output_dir(exp_dir)
        research_state = ResearchState()
        write_json(exp_dir / "research_state.json", research_state.to_dict())

        spec = read_yaml(scenario_dir / "task_spec.yaml")
        default_config = read_yaml(policy_dir / "default_config.yaml")
        search_space = read_yaml(policy_dir / "search_space.yaml")
        metadata_path = policy_dir / "metadata.json"
        policy_metadata = (
            read_json(metadata_path)
            if metadata_path.is_file()
            else {
                "policy_id": policy_dir.name,
                "policy_type": default_config.get("policy_type", "unknown"),
            }
        )
        evaluation_metrics = spec.get("evaluation_metrics", {})
        seeds = _trial_seeds(spec, search_space)
        requires_training = _requires_training(policy_metadata)
        baseline_mode = str(
            search_space.get("baseline", {}).get(
                "mode",
                "trained_default" if requires_training else "default_config",
            )
        )
        baseline_identity = str(
            search_space.get("baseline", {}).get(
                "identity",
                (
                    "policy.default_config_trained"
                    if requires_training
                    else "policy.default_config"
                ),
            )
        )
        baseline_config_path = exp_dir / "baseline_config.yaml"
        write_yaml(baseline_config_path, default_config)
        baseline_checkpoint = None
        if requires_training and baseline_mode != "untrained":
            baseline_checkpoint = self._train_policy(
                policy_dir=policy_dir,
                scenario_dir=scenario_dir,
                config_path=baseline_config_path,
                output_dir=exp_dir / "baseline_training",
                search_space=search_space,
            )
        baseline_metrics, baseline_per_seed_metrics = _evaluate(
            policy_dir,
            spec,
            default_config,
            seeds,
            checkpoint_path=baseline_checkpoint,
        )
        write_json(
            exp_dir / "baseline_metrics.json",
            {
                "schema_version": "1.0",
                "config_source": baseline_identity,
                "training_executed": baseline_checkpoint is not None,
                "seeds": seeds,
                "metrics": baseline_metrics,
                "per_seed_metrics": baseline_per_seed_metrics,
                "statistics": _per_seed_statistics(baseline_per_seed_metrics),
                "checkpoint_path": (
                    baseline_checkpoint.relative_to(exp_dir).as_posix()
                    if baseline_checkpoint is not None
                    else None
                ),
            },
        )

        rows: list[dict[str, Any]] = []
        for index, config in enumerate(_expand_configs(default_config, search_space), start=1):
            trial_id = f"trial_{index:04d}"
            trial_dir = exp_dir / "trials" / trial_id
            trial_dir.mkdir(parents=True, exist_ok=True)
            config_path = trial_dir / "config.yaml"
            write_yaml(config_path, config)

            started = time.perf_counter()
            checkpoint_path = None
            if requires_training:
                checkpoint_path = self._train_policy(
                    policy_dir=policy_dir,
                    scenario_dir=scenario_dir,
                    config_path=config_path,
                    output_dir=trial_dir,
                    search_space=search_space,
                )
            metrics, per_seed_metrics = _evaluate(
                policy_dir,
                spec,
                config,
                seeds,
                checkpoint_path=checkpoint_path,
            )
            ranking_key(metrics, evaluation_metrics)
            log = {
                "trial_id": trial_id,
                "scenario_id": spec.get("task_id", scenario_dir.name),
                "policy_id": policy_dir.name,
                "seeds": seeds,
                "wall_time_seconds": float(time.perf_counter() - started),
                "training_executed": requires_training,
                "checkpoint_path": (
                    checkpoint_path.relative_to(exp_dir).as_posix()
                    if checkpoint_path is not None
                    else None
                ),
                "checkpoint_hash": (
                    f"sha256:{_sha256(checkpoint_path)}"
                    if checkpoint_path is not None
                    else None
                ),
            }
            write_json(trial_dir / "metrics.json", metrics)
            write_json(
                trial_dir / "per_seed_metrics.json",
                {
                    "schema_version": "1.0",
                    "seeds": seeds,
                    "metrics": per_seed_metrics,
                    "statistics": _per_seed_statistics(per_seed_metrics),
                },
            )
            write_json(trial_dir / "log.json", log)

            rows.append(
                {
                    "trial_id": trial_id,
                    "trial_index": index,
                    "config": config,
                    "metrics": metrics,
                    "per_seed_metrics": per_seed_metrics,
                }
            )

        ranked_rows = sorted(
            rows,
            key=lambda item: ranking_key(item["metrics"], evaluation_metrics),
        )
        best = ranked_rows[0]
        succeeded = ranking_key(
            best["metrics"],
            evaluation_metrics,
        ) < ranking_key(baseline_metrics, evaluation_metrics)
        research_state.record_stage_result(
            succeeded=succeeded,
            reason=(
                "stage 1 produced a promotable candidate against the declared baseline"
                if succeeded
                else "stage 1 did not improve the declared baseline"
            ),
        )
        write_json(exp_dir / "research_state.json", research_state.to_dict())
        _write_leaderboard(exp_dir / "leaderboard.csv", ranked_rows)
        write_yaml(exp_dir / "best_config.yaml", best["config"])
        generate_training_visualizations(
            exp_dir=exp_dir,
            scenario_spec=spec,
            policy_metadata=policy_metadata,
            search_space=search_space,
            rows=rows,
            baseline_metrics=baseline_metrics,
            baseline_per_seed_metrics=baseline_per_seed_metrics,
            best=best,
            seeds=seeds,
            baseline_identity=baseline_identity,
        )
        (exp_dir / "report.md").write_text(
            _report(
                exp_id,
                best,
                baseline_metrics,
                baseline_per_seed_metrics,
                evaluation_metrics,
                baseline_identity,
            ),
            encoding="utf-8",
        )
        write_json(exp_dir / "manifest.json", build_manifest(exp_dir, "experiment", exp_id))
        return exp_dir

    def _train_policy(
        self,
        *,
        policy_dir: Path,
        scenario_dir: Path,
        config_path: Path,
        output_dir: Path,
        search_space: dict[str, Any],
    ) -> Path:
        budget = search_space.get("budget", {})
        max_steps = int(budget.get("max_train_steps", 4_000))
        wall_time_limit = float(budget.get("wall_time_limit_seconds", 300.0))
        log_interval = int(budget.get("log_interval", max(max_steps // 5, 1)))
        train_seed = int(budget.get("train_seed", 0))
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str((policy_dir / "train.py").resolve()),
            "--config",
            str(config_path.resolve()),
            "--scenario",
            str(scenario_dir.resolve()),
            "--seed",
            str(train_seed),
            "--output_dir",
            str(output_dir.resolve()),
            "--max_steps",
            str(max_steps),
            "--wall_time_limit",
            str(wall_time_limit),
            "--log_interval",
            str(log_interval),
        ]
        environment = os.environ.copy()
        source_root = str((self.project_root / "src").resolve())
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            os.pathsep.join([source_root, existing_pythonpath])
            if existing_pythonpath
            else source_root
        )
        timeout = max(wall_time_limit + 30.0, 30.0)
        completed = subprocess.run(
            command,
            cwd=self.project_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        (output_dir / "trainer_process.log").write_text(
            completed.stdout + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"policy training failed with exit code {completed.returncode}; "
                f"see {output_dir / 'trainer_process.log'}"
            )
        training_log_path = output_dir / "training_log.json"
        if not training_log_path.is_file():
            raise FileNotFoundError(
                f"policy trainer did not emit training_log.json: {training_log_path}"
            )
        training_log = read_json(training_log_path)
        checkpoint_name = training_log.get("checkpoint_path")
        if not isinstance(checkpoint_name, str) or not checkpoint_name:
            raise ValueError("training_log.checkpoint_path must be a non-empty string")
        checkpoint_path = output_dir / checkpoint_name
        if not checkpoint_path.is_file():
            raise FileNotFoundError(
                f"policy trainer checkpoint does not exist: {checkpoint_path}"
            )
        curve_path = output_dir / "training_curves.csv"
        if not curve_path.is_file():
            raise FileNotFoundError(
                f"policy trainer did not emit training_curves.csv: {curve_path}"
            )
        return checkpoint_path


def evaluate_policy_dir(
    policy_dir: Path,
    scenario_dir: Path,
    config_path: Path | None = None,
    seeds: list[int] | None = None,
    checkpoint: Path | None = None,
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
    metrics, per_seed_metrics = _evaluate(
        policy_dir,
        spec,
        config,
        selected_seeds,
        checkpoint_path=Path(checkpoint) if checkpoint else None,
    )
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
    checkpoint_path: Path | None = None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    PolicyClass = _load_policy_class(policy_dir)
    per_seed_metrics = [
        _run_episode(
            PolicyClass,
            spec,
            config,
            int(seed),
            checkpoint_path=checkpoint_path,
        )
        for seed in seeds
    ]
    count = max(len(per_seed_metrics), 1)
    metrics = {
        "success_rate": sum(item["success_rate"] for item in per_seed_metrics) / count,
        "collision_rate": sum(item["collision_rate"] for item in per_seed_metrics) / count,
        "out_of_bounds_rate": sum(item["out_of_bounds_rate"] for item in per_seed_metrics) / count,
        "avg_episode_length": sum(item["episode_length"] for item in per_seed_metrics) / count,
        "action_violation_rate": sum(item["action_violation_rate"] for item in per_seed_metrics) / count,
    }
    return metrics, per_seed_metrics


def _per_seed_statistics(
    per_seed_metrics: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    if not per_seed_metrics:
        return {}
    output_names = {
        "success_rate": "success_rate",
        "collision_rate": "collision_rate",
        "out_of_bounds_rate": "out_of_bounds_rate",
        "episode_length": "avg_episode_length",
        "action_violation_rate": "action_violation_rate",
    }
    statistics: dict[str, dict[str, float | int]] = {}
    for source_name, output_name in output_names.items():
        values = np.asarray(
            [float(item[source_name]) for item in per_seed_metrics],
            dtype=float,
        )
        statistics[output_name] = {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=0)),
            "n": int(values.size),
        }
    return statistics


def _run_episode(
    PolicyClass: type,
    spec: dict[str, Any],
    config: dict[str, Any],
    seed: int,
    *,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    env = create_runtime(spec)
    policy = PolicyClass(config, spec)
    if checkpoint_path is not None:
        policy.load(str(checkpoint_path))
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


def _requires_training(policy_metadata: dict[str, Any]) -> bool:
    method = policy_metadata.get("method", {})
    paradigm = str(method.get("learning_paradigm", "none")).strip().lower()
    return paradigm not in {"", "none", "rule", "rule_based", "not_applicable"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _report(
    exp_id: str,
    best: dict[str, Any],
    baseline_metrics: dict[str, float],
    baseline_per_seed_metrics: list[dict[str, Any]],
    evaluation_metrics: dict[str, Any],
    baseline_identity: str,
) -> str:
    metrics = best["metrics"]
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    direction = str(primary.get("direction", "maximize"))
    metric_rows = _report_metric_rows(
        baseline_metrics,
        metrics,
        baseline_per_seed_metrics,
        best.get("per_seed_metrics", []),
        evaluation_metrics,
    )
    table = "\n".join(
        f"| {name} | {metric_direction} | {baseline:.4g} ± {baseline_std:.3g} | "
        f"{candidate:.4g} ± {candidate_std:.3g} | "
        f"{candidate - baseline:+.4g} |"
        for (
            name,
            metric_direction,
            baseline,
            baseline_std,
            candidate,
            candidate_std,
        ) in metric_rows
    )
    direction_delta = (
        float(metrics[primary_name]) - float(baseline_metrics[primary_name])
        if direction == "maximize"
        else float(baseline_metrics[primary_name]) - float(metrics[primary_name])
    )
    return (
        f"# AutoResearch Report: {exp_id}\n\n"
        "## Outcome\n\n"
        f"- Best trial: `{best['trial_id']}`\n"
        f"- Primary metric: `{primary_name}` ({direction})\n"
        f"- Baseline: `{baseline_identity}`\n"
        f"- Direction-aware improvement over baseline: {direction_delta:+.4g}\n\n"
        "## Raw comparison table\n\n"
        "| Metric | Direction | Baseline mean ± std | Best mean ± std | Raw delta |\n"
        "|---|---:|---:|---:|---:|\n"
        f"{table}\n\n"
        "## Standard visualizations\n\n"
        "- [Training design](figures/training_design.png)\n"
        "- [Training process](figures/training_process.png)\n"
        "- [Training effect](figures/training_effect.png)\n"
        "- [Visualization manifest](figures/visualization_manifest.json)\n\n"
        "Training reward is explanatory only. Promotion remains governed by "
        "`scenario.evaluation_metrics` and hard constraints.\n"
    )


def _report_metric_rows(
    baseline: dict[str, float],
    candidate: dict[str, float],
    baseline_per_seed: list[dict[str, Any]],
    candidate_per_seed: list[dict[str, Any]],
    evaluation_metrics: dict[str, Any],
) -> list[tuple[str, str, float, float, float, float]]:
    directions: dict[str, str] = {}
    primary = evaluation_metrics.get("primary", {})
    primary_name = str(primary.get("name", "success_rate"))
    directions[primary_name] = str(primary.get("direction", "maximize"))
    for item in evaluation_metrics.get("secondary", []):
        source_name = str(item.get("name", ""))
        output_name = "avg_episode_length" if source_name == "episode_length" else source_name
        directions[output_name] = str(item.get("direction", "minimize"))
    for item in evaluation_metrics.get("hard_constraints", []):
        name = str(item.get("name", ""))
        directions[name] = str(item.get("direction", "minimize"))
    return [
        (
            name,
            direction,
            float(baseline[name]),
            _per_seed_metric_std(baseline_per_seed, name),
            float(candidate[name]),
            _per_seed_metric_std(candidate_per_seed, name),
        )
        for name, direction in directions.items()
        if name in baseline and name in candidate
    ]


def _per_seed_metric_std(
    per_seed_metrics: list[dict[str, Any]],
    output_name: str,
) -> float:
    source_name = "episode_length" if output_name == "avg_episode_length" else output_name
    values = [
        float(item[source_name])
        for item in per_seed_metrics
        if source_name in item
    ]
    return float(np.std(values, ddof=0)) if values else 0.0
