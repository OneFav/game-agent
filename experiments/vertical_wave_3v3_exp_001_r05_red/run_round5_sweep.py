from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SCENARIO_DIR = ROOT / "scenarios" / "vertical_wave_3v3_001"
POLICY_DIR = ROOT / "policies" / "vertical_wave_3v3_rule_v1_r05_red"
EXP_DIR = ROOT / "experiments" / "vertical_wave_3v3_exp_001_r05_red"
TARGET_SIDE = "red"
FROZEN_OPPONENT = "blue"
BASELINE_RED_UTILITY = 5.0
BEST_RESPONSE_GAIN_BLUE = 0.3333333333333339
IMPROVEMENT_THRESHOLD = 0.02
CODE_ITERATIONS = 10


def main() -> int:
    spec = read_yaml(SCENARIO_DIR / "task_spec.yaml")
    search_space = read_yaml(POLICY_DIR / "search_space.yaml")
    default_config = read_yaml(POLICY_DIR / "default_config.yaml")
    seeds = [int(seed) for seed in spec["splits"]["eval"]["seeds"]]

    EXP_DIR.mkdir(parents=True, exist_ok=True)
    (EXP_DIR / "trials").mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    configs = expand_configs(default_config, search_space)
    for index, config in enumerate(configs, start=1):
        trial_id = f"trial_{index:04d}"
        hypothesis = make_hypothesis(config, default_config)
        trial_dir = EXP_DIR / "trials" / trial_id
        trial_dir.mkdir(parents=True, exist_ok=True)
        config_path = trial_dir / "config.yaml"
        checkpoint_dir = trial_dir / "checkpoint"
        infer_path = trial_dir / "infer_results.json"

        metrics_path = trial_dir / "metrics.json"
        log_path = trial_dir / "log.json"
        if os.environ.get("ROUND5_FORCE_RERUN") != "1" and metrics_path.is_file() and log_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            log = json.loads(log_path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "trial_id": trial_id,
                    "config": read_yaml(config_path) if config_path.is_file() else config,
                    "metrics": metrics,
                    "hypothesis": log.get("hypothesis", hypothesis),
                }
            )
            continue

        write_yaml(config_path, config)

        started = time.perf_counter()
        train_cmd = [
            sys.executable,
            str(POLICY_DIR / "train.py"),
            "--config",
            str(config_path),
            "--scenario",
            str(SCENARIO_DIR),
            "--seed",
            str(seeds[0]),
            "--output_dir",
            str(checkpoint_dir),
            "--max_steps",
            "600",
            "--wall_time_limit",
            "30",
        ]
        infer_cmd = [
            sys.executable,
            str(POLICY_DIR / "infer.py"),
            "--checkpoint",
            str(checkpoint_dir / "checkpoint.json"),
            "--scenario",
            str(SCENARIO_DIR),
            "--eval_seeds",
            ",".join(str(seed) for seed in seeds),
            "--output",
            str(infer_path),
        ]
        train_run = subprocess.run(train_cmd, cwd=ROOT, text=True, capture_output=True)
        infer_run = subprocess.run(infer_cmd, cwd=ROOT, text=True, capture_output=True)
        if train_run.returncode != 0 or infer_run.returncode != 0:
            metrics = failed_metrics(train_run, infer_run)
            infer_results: dict[str, Any] = {}
        else:
            infer_results = json.loads(infer_path.read_text(encoding="utf-8"))
            metrics = flatten_infer_results(infer_results)

        metrics["target_side"] = TARGET_SIDE
        metrics["target_side_score"] = metrics["red_score"]
        metrics["red_utility_minus_blue_utility"] = metrics["red_score"] - metrics["blue_score"]
        metrics["advantage_score"] = metrics["red_utility_minus_blue_utility"]
        metrics["hard_constraints_passed"] = hard_constraints_passed(metrics)
        metrics["target_gate_passed"] = metrics["red_utility_minus_blue_utility"] > 0.0
        metrics["best_response_gain_side"] = metrics["red_score"] - BASELINE_RED_UTILITY
        metrics["promotion_gate_passed"] = bool(
            metrics["hard_constraints_passed"]
            and metrics["red_score"] >= BASELINE_RED_UTILITY + IMPROVEMENT_THRESHOLD
            and metrics["target_gate_passed"]
            and schema_consistent(config)
        )
        metrics["decision"] = decision(metrics)
        metrics["failure_episodes"] = infer_results.get("failure_episodes", [])
        metrics["per_seed_metrics"] = infer_results.get("per_seed_metrics", [])

        log = {
            "trial_id": trial_id,
            "target_side": TARGET_SIDE,
            "frozen_opponent": FROZEN_OPPONENT,
            "hypothesis": hypothesis,
            "modified": "parameters",
            "seeds": seeds,
            "train_command": train_cmd,
            "infer_command": infer_cmd,
            "train_returncode": train_run.returncode,
            "infer_returncode": infer_run.returncode,
            "train_stderr": train_run.stderr,
            "infer_stderr": infer_run.stderr,
            "wall_time_seconds": time.perf_counter() - started,
            "target_passed": metrics["target_gate_passed"],
            "hard_constraints_passed": metrics["hard_constraints_passed"],
            "failure_reason": failure_reason(metrics),
        }
        write_json(trial_dir / "metrics.json", metrics)
        write_json(trial_dir / "log.json", log)
        rows.append({"trial_id": trial_id, "config": config, "metrics": metrics, "hypothesis": hypothesis})

    rows.sort(key=lambda row: ranking_key(row["metrics"]))
    best = rows[0]
    coupling = run_coupling_load_test(best["config"], float(best["metrics"]["red_score"]), seeds)
    best["metrics"]["coupling_load_delta"] = coupling["delta"]
    best["metrics"]["coupling_load_passed"] = coupling["passed"]
    best["metrics"]["decision"] = "promotion" if final_passed(best["metrics"]) else best["metrics"]["decision"]
    write_json(EXP_DIR / "trials" / best["trial_id"] / "metrics.json", best["metrics"])

    write_leaderboard(rows)
    write_yaml(EXP_DIR / "best_config.yaml", best["config"])
    write_json(EXP_DIR / "coupling_load_test.json", coupling)
    write_json(EXP_DIR / "sweep_summary.json", sweep_summary(rows, best, coupling))
    (EXP_DIR / "regression_report.md").write_text(regression_report(rows, best, coupling), encoding="utf-8")
    (EXP_DIR / "report.md").write_text(report(rows, best, coupling), encoding="utf-8")
    write_json(EXP_DIR / "manifest.json", build_manifest())
    return 0


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def expand_configs(default_config: dict[str, Any], search_space: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = search_space["parameters"]
    priority_1 = list(search_space["priority_groups"]["priority_1"])
    max_trials = int(search_space["budget"]["max_trials"])
    full_grid = [dict(zip(priority_1, values)) for values in itertools.product(*(parameters[name]["values"] for name in priority_1))]

    default_point = {name: default_config[name] for name in priority_1}
    selected: list[dict[str, Any]] = []
    if default_point in full_grid:
        selected.append(default_point)

    remaining_slots = max_trials - len(selected)
    if remaining_slots > 0:
        candidates = [point for point in full_grid if point not in selected]
        if len(candidates) <= remaining_slots:
            selected.extend(candidates)
        else:
            step = (len(candidates) - 1) / max(remaining_slots - 1, 1)
            used: set[int] = set()
            for slot in range(remaining_slots):
                idx = int(round(slot * step))
                while idx in used and idx + 1 < len(candidates):
                    idx += 1
                used.add(idx)
                selected.append(candidates[idx])

    configs: list[dict[str, Any]] = []
    for point in selected[:max_trials]:
        config = dict(default_config)
        config.update(point)
        for name in search_space["priority_groups"].get("do_not_tune", []):
            config[name] = default_config[name]
        configs.append(config)
    return configs


def make_hypothesis(config: dict[str, Any], default_config: dict[str, Any]) -> str:
    changed = [
        f"{name}={config[name]}"
        for name in (
            "red_desired_speed",
            "red_risk_margin",
            "red_lane_spacing",
            "red_breakout_gain",
            "red_escape_gain",
            "red_screen_gain",
        )
        if config[name] != default_config[name]
    ]
    if not changed:
        return "Baseline red parameters should establish the Round 5 score against frozen Round 4 blue."
    return "Changing " + ", ".join(changed) + " should improve red gate progress without violating safety constraints."


def flatten_infer_results(results: dict[str, Any]) -> dict[str, Any]:
    metrics = results["metrics"]
    hard = metrics["hard_constraints"]
    secondary = metrics["secondary"]
    per_seed = results.get("per_seed_metrics", [])
    red_scores = [float(item["red_score"]) for item in per_seed]
    return {
        "red_score": float(secondary["red_score"]["value"]),
        "blue_score": float(secondary["blue_score"]["value"]),
        "collision_rate": float(hard["collision_rate"]["value"]),
        "out_of_bounds_rate": float(hard["out_of_bounds_rate"]["value"]),
        "action_violation_rate": float(hard["action_violation_rate"]["value"]),
        "avg_episode_length": float(secondary["avg_episode_length"]["value"]),
        "primary_std": float(np.std(red_scores)) if red_scores else float(metrics["primary"].get("std", 0.0)),
    }


def failed_metrics(train_run: subprocess.CompletedProcess[str], infer_run: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    del train_run, infer_run
    return {
        "red_score": float("-inf"),
        "blue_score": float("inf"),
        "collision_rate": 1.0,
        "out_of_bounds_rate": 1.0,
        "action_violation_rate": 1.0,
        "avg_episode_length": float("inf"),
        "primary_std": float("inf"),
    }


def hard_constraints_passed(metrics: dict[str, Any]) -> bool:
    return (
        float(metrics["collision_rate"]) <= 0.05
        and float(metrics["out_of_bounds_rate"]) <= 0.01
        and float(metrics["action_violation_rate"]) <= 0.0
    )


def schema_consistent(config: dict[str, Any]) -> bool:
    import importlib.util

    spec = importlib.util.spec_from_file_location("round5_policy_schema", POLICY_DIR / "policy.py")
    if spec is None or spec.loader is None:
        return False
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = module.PolicyClass().get_config_schema()
    for name, value in config.items():
        if name not in schema:
            return False
        rule = schema[name]
        if rule["type"] == "string" and value not in rule["enum"]:
            return False
        if rule["type"] != "string" and (float(value) < float(rule["minimum"]) or float(value) > float(rule["maximum"])):
            return False
    return True


def decision(metrics: dict[str, Any]) -> str:
    if not metrics["hard_constraints_passed"]:
        return "rollback"
    if metrics["promotion_gate_passed"]:
        return "promotion"
    return "continue"


def failure_reason(metrics: dict[str, Any]) -> str:
    if not metrics["hard_constraints_passed"]:
        return "hard_constraints_failed"
    if not metrics["target_gate_passed"]:
        return "red_utility_minus_blue_utility_not_positive"
    if not metrics["promotion_gate_passed"]:
        return "promotion_gate_not_passed"
    return ""


def ranking_key(metrics: dict[str, Any]) -> tuple[object, ...]:
    feasible = hard_constraints_passed(metrics)
    red_score = float(metrics["red_score"])
    avg_episode_length = float(metrics["avg_episode_length"])
    return (not feasible, -red_score, avg_episode_length)


def run_coupling_load_test(config: dict[str, Any], true_red_score: float, seeds: list[int]) -> dict[str, Any]:
    per_seed = run_zero_opponent_eval(config, seeds, zero_side="blue")
    empty_score = sum(item["red_score"] for item in per_seed) / max(len(per_seed), 1)
    delta = empty_score - true_red_score
    return {
        "target_side": TARGET_SIDE,
        "utility_side": "red",
        "utility_source": "avg_red_score / avg_blue_score from evaluator score outputs",
        "seeds": seeds,
        "true_opponent_score": true_red_score,
        "empty_field_score": empty_score,
        "delta": delta,
        "passed": delta > 0.0,
        "per_seed": per_seed,
    }


def run_zero_opponent_eval(config: dict[str, Any], seeds: list[int], zero_side: str) -> list[dict[str, Any]]:
    import importlib.util

    env_spec = importlib.util.spec_from_file_location("round5_env", SCENARIO_DIR / "env.py")
    policy_spec = importlib.util.spec_from_file_location("round5_policy", POLICY_DIR / "policy.py")
    if env_spec is None or env_spec.loader is None or policy_spec is None or policy_spec.loader is None:
        raise RuntimeError("cannot load env or policy")
    env_module = importlib.util.module_from_spec(env_spec)
    policy_module = importlib.util.module_from_spec(policy_spec)
    env_spec.loader.exec_module(env_module)
    policy_spec.loader.exec_module(policy_module)

    results: list[dict[str, Any]] = []
    for seed in seeds:
        env = env_module.make_env()
        policy = policy_module.PolicyClass(config, read_yaml(SCENARIO_DIR / "task_spec.yaml"))
        policy.reset(seed)
        _observations, infos = env.reset(seed=seed)
        action_violations = 0
        for _ in range(1, int(getattr(env, "max_steps", 600)) + 1):
            actions = policy.compute_actions(env)
            for agent_id in list(actions):
                if str(agent_id).startswith(zero_side):
                    actions[agent_id] = np.zeros(env.action_shape, dtype=np.float32)
                action_array = np.asarray(actions[agent_id], dtype=np.float32)
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
        steps = int(env.base_env.step_count)
        denom = max(steps * len(getattr(env, "agents", [])), 1)
        results.append(
            {
                "seed": int(seed),
                "red_score": float(red_info.get("team_score", 0.0)),
                "blue_score": float(blue_info.get("team_score", 0.0)),
                "side_score": float(red_info.get("team_score", 0.0)),
                "collision": any(bool(info.get("collision", False)) for info in infos.values()),
                "out_of_bounds": any(bool(info.get("out_of_bounds", False)) for info in infos.values()),
                "episode_length": steps,
                "action_violation_rate": float(action_violations / denom),
            }
        )
    return results


def final_passed(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["hard_constraints_passed"]
        and metrics["target_gate_passed"]
        and metrics.get("coupling_load_passed", False)
    )


def write_leaderboard(rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "rank",
        "trial_id",
        "feasible",
        "promotion_gate_passed",
        "target_gate_passed",
        "target_side",
        "red_score",
        "blue_score",
        "red_utility_minus_blue_utility",
        "advantage_score",
        "collision_rate",
        "out_of_bounds_rate",
        "action_violation_rate",
        "avg_episode_length",
        "primary_std",
        "coupling_load_delta",
        "best_response_gain_side",
        "decision",
    ]
    with (EXP_DIR / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            metrics = row["metrics"]
            writer.writerow(
                {
                    "rank": rank,
                    "trial_id": row["trial_id"],
                    "feasible": str(bool(metrics["hard_constraints_passed"])).lower(),
                    "promotion_gate_passed": str(bool(metrics["promotion_gate_passed"])).lower(),
                    "target_gate_passed": str(bool(metrics["target_gate_passed"])).lower(),
                    "target_side": TARGET_SIDE,
                    "red_score": fnum(metrics["red_score"]),
                    "blue_score": fnum(metrics["blue_score"]),
                    "red_utility_minus_blue_utility": fnum(metrics["red_utility_minus_blue_utility"]),
                    "advantage_score": fnum(metrics["advantage_score"]),
                    "collision_rate": fnum(metrics["collision_rate"]),
                    "out_of_bounds_rate": fnum(metrics["out_of_bounds_rate"]),
                    "action_violation_rate": fnum(metrics["action_violation_rate"]),
                    "avg_episode_length": fnum(metrics["avg_episode_length"]),
                    "primary_std": fnum(metrics["primary_std"]),
                    "coupling_load_delta": "" if "coupling_load_delta" not in metrics else fnum(metrics["coupling_load_delta"]),
                    "best_response_gain_side": fnum(metrics["best_response_gain_side"]),
                    "decision": metrics["decision"],
                }
            )


def fnum(value: Any) -> str:
    numeric = float(value)
    if math.isinf(numeric):
        return str(numeric)
    return f"{numeric:.6f}"


def sweep_summary(rows: list[dict[str, Any]], best: dict[str, Any], coupling: dict[str, Any]) -> dict[str, Any]:
    return {
        "trial_count": len(rows),
        "baseline_red_utility": BASELINE_RED_UTILITY,
        "best_trial": best["trial_id"],
        "best_metrics": best["metrics"],
        "coupling_load_test": coupling,
        "scenario_freeze_hash": read_manifest_hash(SCENARIO_DIR / "manifest.json"),
        "policy_freeze_hash": read_manifest_hash(POLICY_DIR / "manifest.json"),
        "code_iterations": CODE_ITERATIONS,
        "target_side": TARGET_SIDE,
        "status": "PASS" if final_passed(best["metrics"]) else "FAIL",
    }


def report(rows: list[dict[str, Any]], best: dict[str, Any], coupling: dict[str, Any]) -> str:
    metrics = best["metrics"]
    top3 = rows[:3]
    status = "PASS" if final_passed(metrics) else "FAIL"
    advantage_line = (
        f"- `advantage_score = red_utility - blue_utility = {metrics['advantage_score']:.3f}`; red is advantaged because this value is greater than 0."
        if float(metrics["advantage_score"]) > 0.0
        else f"- `advantage_score = red_utility - blue_utility = {metrics['advantage_score']:.3f}`; red is not advantaged because this value is not greater than 0."
    )
    return "\n".join(
        [
            "# AutoResearch Round 5: red",
            "",
            "## Scope",
            "- Scenario: `scenarios/vertical_wave_3v3_001/`",
            "- Policy: `policies/vertical_wave_3v3_rule_v1_r05_red/`",
            "- Target side: `red`; frozen opponent: `blue` from Round 4 best trial `trial_0007`.",
            "- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.",
            f"- Sweep: {len(rows)} trials from `search_space.yaml` priority_1 budget; code iterations: {CODE_ITERATIONS}.",
            "- Ranking: feasible hard constraints first, then primary evaluation metric `team_score`/red utility descending, then `avg_episode_length` ascending.",
            "",
            "## Best Trial",
            f"- Best trial: `{best['trial_id']}`",
            f"- red_utility: {metrics['red_score']:.3f}",
            f"- blue_utility: {metrics['blue_score']:.3f}",
            f"- red_utility - blue_utility: {metrics['red_utility_minus_blue_utility']:.3f}",
            f"- hard_constraints: collision_rate={metrics['collision_rate']:.3f}, out_of_bounds_rate={metrics['out_of_bounds_rate']:.3f}, action_violation_rate={metrics['action_violation_rate']:.3f}",
            f"- primary std across seeds: {metrics['primary_std']:.3f}",
            f"- best_response_gain_red: {metrics['best_response_gain_side']:.3f}",
            f"- coupling load: U_R(red,empty_blue)={coupling['empty_field_score']:.3f}, U_R(red,true_blue)={coupling['true_opponent_score']:.3f}, Delta_R={coupling['delta']:.3f}",
            f"- decision: {status}",
            "",
            "## Hypotheses And Results",
            f"- Baseline hypothesis: {rows_by_trial(rows)['trial_0001']['hypothesis']}",
            f"- Winning hypothesis: {best['hypothesis']}",
            "- The initial parameter-only sweep failed the red advantage target. Code iterations 1-6 explored defender standoff variants but could not satisfy safety and target together; code iteration 7 added red racer vertical split-lane drive; code iteration 8 added a red gate-frame guard; code iteration 9 disabled split-lane dispatch after gate-frame regressions; code iteration 10 added a small red-only comeback boost when red trails. BluePolicy and frozen blue parameters were not changed.",
            "",
            "## Leaderboard Top 3",
            *[
                f"{idx}. `{row['trial_id']}`: feasible={row['metrics']['hard_constraints_passed']}, red-blue={row['metrics']['red_utility_minus_blue_utility']:.3f}, red_score={row['metrics']['red_score']:.3f}, collision={row['metrics']['collision_rate']:.3f}, Delta_R={row['metrics'].get('coupling_load_delta', 'n/a')}"
                for idx, row in enumerate(top3, start=1)
            ],
            "",
            "## Terminal Game Analysis",
            advantage_line,
            f"- `best_response_gain_red = {metrics['best_response_gain_side']:.3f}` versus the Round 4 frozen-blue baseline red utility of {BASELINE_RED_UTILITY:.3f}.",
            f"- `best_response_gain_blue = {BEST_RESPONSE_GAIN_BLUE:.3f}` from the most recent completed blue optimization round.",
            "- Empirical approximate Nash stability is not claimed: at least one recent best-response gain is positive in this finite search space.",
            "",
            "## Iteration Record",
            "- target_side: red",
            "- frozen opponent: blue",
            f"- parameter sweep trials: {len(rows)}",
            f"- controlled policy code iterations: {CODE_ITERATIONS}",
            f"- final status: {status}",
            "",
            "## Validation",
            "- Final experiment package must be validated with `python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r05_red`.",
        ]
    ) + "\n"


def rows_by_trial(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["trial_id"]: row for row in rows}


def regression_report(rows: list[dict[str, Any]], best: dict[str, Any], coupling: dict[str, Any]) -> str:
    rollbacks = [row for row in rows if row["metrics"]["decision"] == "rollback"]
    continues = [row for row in rows if row["metrics"]["decision"] == "continue"]
    return "\n".join(
        [
            "# Regression Report: Round 5 red",
            "",
            f"- Rollback trials: {len(rollbacks)}",
            f"- Continue trials: {len(continues)}",
            f"- Best trial: `{best['trial_id']}`",
            f"- Coupling Delta_R: {coupling['delta']:.3f}",
            "- Rollback notes: infeasible trials were not promoted; non-best feasible trials remain logged in `trials/` and `leaderboard.csv`.",
        ]
    ) + "\n"


def read_manifest_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return str(json.loads(path.read_text(encoding="utf-8")).get("freeze_hash", ""))


def build_manifest() -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[str] = []
    for path in sorted(EXP_DIR.rglob("*")):
        if not path.is_file() or path.name == "manifest.json" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(EXP_DIR).as_posix()
        files.append(rel)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "schema_version": "1.0",
        "package_type": "experiment",
        "package_id": "vertical_wave_3v3_exp_001_r05_red",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": files,
        "freeze_hash": digest.hexdigest(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
