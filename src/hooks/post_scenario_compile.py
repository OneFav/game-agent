from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FILES = (
    "task_spec.yaml",
    "model.md",
    "env_config.yaml",
    "env.py",
    "assumptions.md",
    "manifest.json",
)

REQUIRED_TASK_SPEC_FIELDS = (
    "schema_version",
    "task_id",
    "task_family",
    "formalism",
    "agents",
    "observation_space",
    "action_space",
    "reward_structure",
    "evaluation_metrics",
    "termination_conditions",
    "splits",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a compiled scenario package.")
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()

    errors = validate_scenario(Path(args.scenario))
    if errors:
        print("scenario validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("scenario validation passed")
    return 0


def validate_scenario(scenario_dir: Path) -> list[str]:
    errors: list[str] = []
    if not scenario_dir.is_dir():
        return [f"scenario directory does not exist: {scenario_dir}"]

    errors.extend(_missing_files(scenario_dir, REQUIRED_FILES))
    task_spec = _read_yaml_mapping(scenario_dir / "task_spec.yaml", errors)
    if task_spec is None:
        return errors
    if task_spec == {}:
        errors.append("task_spec.yaml must not be empty")

    for field in REQUIRED_TASK_SPEC_FIELDS:
        if field not in task_spec:
            errors.append(f"task_spec.yaml missing required field: {field}")

    _validate_action_space(task_spec.get("action_space"), errors)
    _validate_metrics(task_spec.get("evaluation_metrics"), task_spec.get("reward_structure"), errors)
    return errors


def _missing_files(root: Path, filenames: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {name}" for name in filenames if not (root / name).is_file()]


def _read_yaml_mapping(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as error:  # pragma: no cover - exact parser errors are PyYAML-specific
        errors.append(f"cannot parse {path.name}: {error}")
        return None
    if data is None:
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} root must be a mapping")
        return None
    return data


def _validate_action_space(action_space: Any, errors: list[str]) -> None:
    if not isinstance(action_space, dict):
        errors.append("action_space must be a mapping")
        return

    shape = action_space.get("shape")
    low = action_space.get("low")
    high = action_space.get("high")
    if not isinstance(shape, list) or len(shape) != 1 or not isinstance(shape[0], int):
        errors.append("action_space.shape must be a one-dimensional integer list")
        return

    expected_len = shape[0]
    for field_name, value in (("low", low), ("high", high)):
        if not isinstance(value, list):
            errors.append(f"action_space.{field_name} must be a list")
        elif len(value) != expected_len:
            errors.append(f"action_space.{field_name} length must match action_space.shape[0]")


def _validate_metrics(evaluation_metrics: Any, reward_structure: Any, errors: list[str]) -> None:
    if not isinstance(evaluation_metrics, dict):
        errors.append("evaluation_metrics must be a mapping")
        return

    primary = evaluation_metrics.get("primary")
    primary_name = primary.get("name") if isinstance(primary, dict) else None
    if not primary_name:
        errors.append("evaluation_metrics.primary.name is required")

    hard_constraints = evaluation_metrics.get("hard_constraints")
    if not isinstance(hard_constraints, list) or not hard_constraints:
        errors.append("evaluation_metrics.hard_constraints must be a non-empty list")

    components = reward_structure.get("components") if isinstance(reward_structure, dict) else None
    if not isinstance(components, list):
        errors.append("reward_structure.components must be a list")
        return

    component_names = {item.get("name") for item in components if isinstance(item, dict)}
    if primary_name in component_names:
        errors.append("evaluation_metrics.primary.name must not equal any reward_structure.components[*].name")


if __name__ == "__main__":
    raise SystemExit(main())
