from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REQUIRED_FILES = (
    "leaderboard.csv",
    "best_config.yaml",
    "baseline_metrics.json",
    "report.md",
    "research_state.json",
    "manifest.json",
)
REQUIRED_TRIAL_FILES = (
    "config.yaml",
    "metrics.json",
    "per_seed_metrics.json",
    "log.json",
)
REQUIRED_FIGURE_FILES = (
    "training_design.png",
    "training_process.png",
    "training_effect.png",
    "visualization_manifest.json",
)
REQUIRED_FIGURE_IDS = {
    "training_design",
    "training_process",
    "training_effect",
}
REQUIRED_TRAINING_CURVE_COLUMNS = {
    "step",
    "episode",
    "reward_mean",
    "actor_loss",
    "critic_loss",
    "evaluation_primary",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AutoResearch experiment run.")
    parser.add_argument("--exp", required=True)
    args = parser.parse_args()

    errors = validate_experiment(Path(args.exp))
    if errors:
        print("experiment validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("experiment validation passed")
    return 0


def validate_experiment(exp_dir: Path) -> list[str]:
    errors: list[str] = []
    if not exp_dir.is_dir():
        return [f"experiment directory does not exist: {exp_dir}"]

    errors.extend(_missing_files(exp_dir, REQUIRED_FILES))
    _validate_trials(exp_dir / "trials", errors)
    _validate_leaderboard(exp_dir / "leaderboard.csv", errors)
    _validate_baseline_metrics(exp_dir / "baseline_metrics.json", errors)
    _validate_research_state(exp_dir / "research_state.json", errors)
    _validate_visualizations(exp_dir / "figures", errors)
    return errors


def _missing_files(root: Path, filenames: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {name}" for name in filenames if not (root / name).is_file()]


def _validate_trials(trials_dir: Path, errors: list[str]) -> None:
    if not trials_dir.is_dir():
        errors.append("trials/ directory is required")
        return

    trial_dirs = [path for path in trials_dir.iterdir() if path.is_dir()]
    if not trial_dirs:
        errors.append("trials/ must contain at least one trial directory")
        return

    for trial_dir in sorted(trial_dirs):
        for filename in REQUIRED_TRIAL_FILES:
            if not (trial_dir / filename).is_file():
                errors.append(f"{trial_dir.name} missing required file: {filename}")
        _validate_training_evidence(trial_dir, errors)


def _validate_training_evidence(trial_dir: Path, errors: list[str]) -> None:
    runner_log_path = trial_dir / "log.json"
    if not runner_log_path.is_file():
        return
    try:
        runner_log = json.loads(runner_log_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(runner_log, dict) or not runner_log.get("training_executed"):
        return

    training_log_path = trial_dir / "training_log.json"
    curve_path = trial_dir / "training_curves.csv"
    for path in (training_log_path, curve_path):
        if not path.is_file():
            errors.append(f"{trial_dir.name} missing learning evidence: {path.name}")
    if not training_log_path.is_file() or not curve_path.is_file():
        return

    try:
        training_log = json.loads(training_log_path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"cannot parse {trial_dir.name}/training_log.json: {error}")
        return
    if not isinstance(training_log, dict):
        errors.append(f"{trial_dir.name}/training_log.json root must be a mapping")
        return
    if training_log.get("status") != "completed":
        errors.append(f"{trial_dir.name} learning run must have completed status")
    checkpoint_name = training_log.get("checkpoint_path")
    if not isinstance(checkpoint_name, str) or not checkpoint_name:
        errors.append(f"{trial_dir.name} training_log.checkpoint_path is required")
    elif not (trial_dir / checkpoint_name).is_file():
        errors.append(f"{trial_dir.name} checkpoint does not exist: {checkpoint_name}")

    try:
        with curve_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            columns = set(reader.fieldnames or [])
    except Exception as error:
        errors.append(f"cannot parse {trial_dir.name}/training_curves.csv: {error}")
        return
    missing_columns = REQUIRED_TRAINING_CURVE_COLUMNS - columns
    if missing_columns:
        errors.append(
            f"{trial_dir.name} training_curves.csv missing columns: "
            + ", ".join(sorted(missing_columns))
        )
    if len(rows) < 2 or len({row.get("step") for row in rows}) < 2:
        errors.append(
            f"{trial_dir.name} learning curve requires at least two distinct steps"
        )


def _validate_leaderboard(path: Path, errors: list[str]) -> None:
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as error:
        errors.append(f"cannot parse leaderboard.csv: {error}")
        return
    if not rows:
        errors.append("leaderboard.csv must contain at least one data row")


def _validate_research_state(path: Path, errors: list[str]) -> None:
    if not path.is_file():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"cannot parse research_state.json: {error}")
        return
    if not isinstance(state, dict):
        errors.append("research_state.json root must be a mapping")
        return
    if state.get("stage") not in (1, 2, 3):
        errors.append("research_state.stage must be 1, 2, or 3")
    if not isinstance(state.get("enabled_capabilities"), list):
        errors.append("research_state.enabled_capabilities must be a list")
    if not isinstance(state.get("history"), list):
        errors.append("research_state.history must be a list")


def _validate_baseline_metrics(path: Path, errors: list[str]) -> None:
    if not path.is_file():
        return
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"cannot parse baseline_metrics.json: {error}")
        return
    if not isinstance(baseline, dict):
        errors.append("baseline_metrics.json root must be a mapping")
        return
    if not isinstance(baseline.get("per_seed_metrics"), list) or not baseline[
        "per_seed_metrics"
    ]:
        errors.append("baseline_metrics.per_seed_metrics must be a non-empty list")
    if not isinstance(baseline.get("statistics"), dict) or not baseline["statistics"]:
        errors.append("baseline_metrics.statistics must be a non-empty mapping")


def _validate_visualizations(figures_dir: Path, errors: list[str]) -> None:
    if not figures_dir.is_dir():
        errors.append("figures/ directory is required")
        return
    errors.extend(_missing_files(figures_dir, REQUIRED_FIGURE_FILES))
    for filename in REQUIRED_FIGURE_FILES:
        path = figures_dir / filename
        if path.suffix == ".png" and path.is_file():
            if path.stat().st_size < 1_000:
                errors.append(f"figure is unexpectedly small: figures/{filename}")
            elif path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                errors.append(f"invalid PNG signature: figures/{filename}")

    manifest_path = figures_dir / "visualization_manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"cannot parse visualization_manifest.json: {error}")
        return
    if not isinstance(manifest, dict):
        errors.append("visualization_manifest.json root must be a mapping")
        return
    if manifest.get("standard") != "training_visualization/v1":
        errors.append(
            "visualization_manifest.standard must be 'training_visualization/v1'"
        )
    figures = manifest.get("figures")
    if not isinstance(figures, list):
        errors.append("visualization_manifest.figures must be a list")
        return
    figure_ids = {
        item.get("id")
        for item in figures
        if isinstance(item, dict)
    }
    missing_ids = REQUIRED_FIGURE_IDS - figure_ids
    if missing_ids:
        errors.append(
            "visualization_manifest missing figure ids: "
            + ", ".join(sorted(missing_ids))
        )
    comparison = manifest.get("comparison")
    if not isinstance(comparison, dict):
        errors.append("visualization_manifest.comparison must be a mapping")
    elif not isinstance(comparison.get("seeds"), list) or not comparison["seeds"]:
        errors.append("visualization_manifest.comparison.seeds must be a non-empty list")
    elif comparison.get("n_seeds") != len(comparison["seeds"]):
        errors.append(
            "visualization_manifest.comparison.n_seeds must match the seed list"
        )


if __name__ == "__main__":
    raise SystemExit(main())
