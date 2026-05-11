from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REQUIRED_FILES = ("leaderboard.csv", "best_config.yaml", "report.md", "manifest.json")
REQUIRED_TRIAL_FILES = ("config.yaml", "metrics.json", "log.json")


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


if __name__ == "__main__":
    raise SystemExit(main())
