from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "scenarios" / "slalom_1v1_3d_001"
POLICY_DIR = ROOT / "policies" / "slalom_1v1_3d_rule_v1"
EXP_DIR = ROOT / "experiments" / "slalom_1v1_3d_exp_001"
TRIALS_DIR = EXP_DIR / "trials"
EVAL_SEEDS = [100, 101, 102]


ROUND1_CONFIGS = [
    {"racer_gain": 0.72, "intercept_gain": 0.60, "avoidance_gain": 0.46},
    {"racer_gain": 0.72, "intercept_gain": 0.74, "avoidance_gain": 0.46},
    {"racer_gain": 0.72, "intercept_gain": 0.88, "avoidance_gain": 0.46},
    {"racer_gain": 0.82, "intercept_gain": 0.60, "avoidance_gain": 0.46},
    {"racer_gain": 0.82, "intercept_gain": 0.74, "avoidance_gain": 0.46},
    {"racer_gain": 0.82, "intercept_gain": 0.88, "avoidance_gain": 0.46},
    {"racer_gain": 0.92, "intercept_gain": 0.60, "avoidance_gain": 0.46},
    {"racer_gain": 0.92, "intercept_gain": 0.74, "avoidance_gain": 0.46},
    {"racer_gain": 0.92, "intercept_gain": 0.88, "avoidance_gain": 0.46},
]


@dataclass
class TrialResult:
    trial_id: str
    round_name: str
    hypothesis: str
    config: dict[str, Any]
    metrics: dict[str, Any]


def main() -> int:
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)

    default_config = _read_yaml(POLICY_DIR / "default_config.yaml")
    results: list[TrialResult] = []

    for index, partial in enumerate(ROUND1_CONFIGS, start=1):
        config = {**default_config, **partial}
        hypothesis = (
            f"round1: racer_gain={config['racer_gain']}, intercept_gain={config['intercept_gain']}, "
            f"avoidance_gain={config['avoidance_gain']} test slalom 1v1 score-vs-safety tradeoff"
        )
        results.append(_run_trial(index, "round1", config, hypothesis))

    best_round1 = _sort_results(results)[0]
    refinement_candidates = _build_round2_configs(default_config, best_round1.config)
    for offset, partial in enumerate(refinement_candidates, start=len(results) + 1):
        config = {**default_config, **partial}
        hypothesis = (
            f"round2: refine around racer_gain={best_round1.config['racer_gain']} / "
            f"intercept_gain={best_round1.config['intercept_gain']} with avoidance={config['avoidance_gain']} "
            f"and boundary={config['boundary_gain']}"
        )
        results.append(_run_trial(offset, "round2", config, hypothesis))

    ranked = _sort_results(results)
    _write_leaderboard(ranked)
    _write_best_config(ranked[0])
    _write_report(ranked)
    _write_manifest()
    print(json.dumps({"best_trial": ranked[0].trial_id, "team_score": ranked[0].metrics["team_score"]}, ensure_ascii=False))
    return 0


def _run_trial(index: int, round_name: str, config: dict[str, Any], hypothesis: str) -> TrialResult:
    trial_id = f"trial_{index:04d}"
    trial_dir = TRIALS_DIR / trial_id
    trial_dir.mkdir(parents=True, exist_ok=True)
    config_path = trial_dir / "config.yaml"
    checkpoint_dir = trial_dir / "checkpoint"
    infer_output = trial_dir / "infer_results.json"

    _write_yaml(config_path, config)
    train_cmd = [
        sys.executable,
        str(POLICY_DIR / "train.py"),
        "--config",
        str(config_path),
        "--scenario",
        str(SCENARIO_DIR),
        "--seed",
        "100",
        "--output_dir",
        str(checkpoint_dir),
        "--max_steps",
        "400",
        "--wall_time_limit",
        "60",
    ]
    infer_cmd = [
        sys.executable,
        str(POLICY_DIR / "infer.py"),
        "--checkpoint",
        str(checkpoint_dir / "checkpoint.json"),
        "--scenario",
        str(SCENARIO_DIR),
        "--eval_seeds",
        ",".join(str(seed) for seed in EVAL_SEEDS),
        "--output",
        str(infer_output),
    ]

    train_result = subprocess.run(train_cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    infer_result = subprocess.run(infer_cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if train_result.returncode != 0:
        raise RuntimeError(f"{trial_id} train failed: {train_result.stderr}")
    if infer_result.returncode != 0:
        raise RuntimeError(f"{trial_id} infer failed: {infer_result.stderr}")

    infer_payload = json.loads(infer_output.read_text(encoding="utf-8"))
    metrics = _flatten_metrics(infer_payload)
    feasible = all(entry["passed"] for entry in infer_payload["metrics"]["hard_constraints"].values())
    decision = "promote" if feasible and metrics["team_score"] >= 1.0 else "continue"

    metrics_payload = {
        **metrics,
        "feasible": feasible,
        "decision": decision,
        "raw_metrics": infer_payload["metrics"],
        "per_seed_metrics": infer_payload["per_seed_metrics"],
    }
    (trial_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (trial_dir / "log.json").write_text(
        json.dumps(
            {
                "trial_id": trial_id,
                "round": round_name,
                "hypothesis": hypothesis,
                "scenario_id": "slalom_1v1_3d_001",
                "policy_id": "slalom_1v1_3d_rule_v1",
                "config": config,
                "train_command": train_cmd,
                "infer_command": infer_cmd,
                "decision": decision,
                "stdout": {"train": train_result.stdout, "infer": infer_result.stdout},
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return TrialResult(trial_id=trial_id, round_name=round_name, hypothesis=hypothesis, config=config, metrics=metrics_payload)


def _build_round2_configs(default_config: dict[str, Any], best_config: dict[str, Any]) -> list[dict[str, Any]]:
    racer_gain = best_config["racer_gain"]
    intercept_gain = best_config["intercept_gain"]
    return [
        {**default_config, "racer_gain": racer_gain, "intercept_gain": intercept_gain, "avoidance_gain": 0.30, "boundary_gain": 0.40},
        {**default_config, "racer_gain": racer_gain, "intercept_gain": intercept_gain, "avoidance_gain": 0.30, "boundary_gain": 0.58},
        {**default_config, "racer_gain": racer_gain, "intercept_gain": intercept_gain, "avoidance_gain": 0.62, "boundary_gain": 0.40},
        {**default_config, "racer_gain": racer_gain, "intercept_gain": intercept_gain, "avoidance_gain": 0.62, "boundary_gain": 0.58},
    ]


def _flatten_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_score": float(payload["metrics"]["primary"]["value"]),
        "blue_team_score": float(payload["metrics"]["secondary"]["blue_team_score"]["value"]),
        "red_win_rate": float(payload["metrics"]["secondary"]["red_win_rate"]["value"]),
        "avg_episode_length": float(payload["metrics"]["secondary"]["avg_episode_length"]["value"]),
        "gate_pass_balance": float(payload["metrics"]["secondary"]["gate_pass_balance"]["value"]),
        "collision_rate": float(payload["metrics"]["hard_constraints"]["collision_rate"]["value"]),
        "out_of_bounds_rate": float(payload["metrics"]["hard_constraints"]["out_of_bounds_rate"]["value"]),
        "action_violation_rate": float(payload["metrics"]["hard_constraints"]["action_violation_rate"]["value"]),
    }


def _sort_results(results: list[TrialResult]) -> list[TrialResult]:
    return sorted(
        results,
        key=lambda item: (
            not bool(item.metrics["feasible"]),
            -float(item.metrics["team_score"]),
            float(item.metrics["avg_episode_length"]),
            float(item.metrics["blue_team_score"]),
        ),
    )


def _write_leaderboard(results: list[TrialResult]) -> None:
    fieldnames = [
        "rank",
        "trial_id",
        "round",
        "feasible",
        "decision",
        "team_score",
        "blue_team_score",
        "red_win_rate",
        "collision_rate",
        "out_of_bounds_rate",
        "action_violation_rate",
        "avg_episode_length",
        "gate_pass_balance",
    ]
    with (EXP_DIR / "leaderboard.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, result in enumerate(results, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "trial_id": result.trial_id,
                    "round": result.round_name,
                    "feasible": result.metrics["feasible"],
                    "decision": result.metrics["decision"],
                    "team_score": result.metrics["team_score"],
                    "blue_team_score": result.metrics["blue_team_score"],
                    "red_win_rate": result.metrics["red_win_rate"],
                    "collision_rate": result.metrics["collision_rate"],
                    "out_of_bounds_rate": result.metrics["out_of_bounds_rate"],
                    "action_violation_rate": result.metrics["action_violation_rate"],
                    "avg_episode_length": result.metrics["avg_episode_length"],
                    "gate_pass_balance": result.metrics["gate_pass_balance"],
                }
            )


def _write_best_config(best: TrialResult) -> None:
    _write_yaml(EXP_DIR / "best_config.yaml", best.config)


def _write_report(results: list[TrialResult]) -> None:
    best = results[0]
    top3 = results[:3]
    lines = [
        "# AutoResearch Report: slalom_1v1_3d_exp_001",
        "",
        "## Sweep Summary",
        "",
        f"- Trials: {len(results)}",
        f"- Eval seeds: {EVAL_SEEDS}",
        f"- Best trial: `{best.trial_id}`",
        f"- Best team_score: {best.metrics['team_score']:.3f}",
        f"- Best blue_team_score: {best.metrics['blue_team_score']:.3f}",
        f"- Best red_win_rate: {best.metrics['red_win_rate']:.3f}",
        f"- Best collision_rate: {best.metrics['collision_rate']:.3f}",
        "",
        "## Iteration Notes",
        "",
        "- Round 1 fixed `avoidance_gain=0.46` and scanned `racer_gain × intercept_gain` to establish a stable score/safety baseline.",
        "- Round 2 fixed the best round-1 `(racer_gain, intercept_gain)` pair and refined `avoidance_gain` plus `boundary_gain` to reduce collisions and keep score above target.",
        "",
        "## Leaderboard Top 3",
        "",
    ]
    for rank, result in enumerate(top3, start=1):
        lines.append(
            f"{rank}. `{result.trial_id}` | round={result.round_name} | team_score={result.metrics['team_score']:.3f} | "
            f"collision_rate={result.metrics['collision_rate']:.3f} | decision={result.metrics['decision']}"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            f"- README target `team_score >= 1.0` {'已满足' if best.metrics['team_score'] >= 1.0 else '未满足'}。",
            "- 排名仅使用 evaluation_metrics 与硬约束，没有使用 reward components 做晋级判断。",
        ]
    )
    (EXP_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from game_agent.utils.manifest import build_manifest

    payload = build_manifest(EXP_DIR, "experiment", "slalom_1v1_3d_exp_001")
    (EXP_DIR / "manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
