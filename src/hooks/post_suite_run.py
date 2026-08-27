from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml


SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from game_agent.visualization.validation import validate_visualization_spec


REQUIRED_FILES = (
    "scenario_results.csv",
    "coverage_matrix.csv",
    "summary.json",
    "state.json",
    "report.md",
    "manifest.json",
)
REQUIRED_FIGURES = (
    "scenario_results_overview.png",
    "coverage_matrix.png",
    "visualization_manifest.json",
)


def validate_suite_run(
    run_dir: Path, *, expected_count: int | None = None
) -> list[str]:
    errors: list[str] = []
    if not run_dir.is_dir():
        return [f"suite run directory does not exist: {run_dir}"]
    for filename in REQUIRED_FILES:
        if not (run_dir / filename).is_file():
            errors.append(f"missing required file: {filename}")
    for filename in REQUIRED_FIGURES:
        path = run_dir / "figures" / filename
        if not path.is_file():
            errors.append(f"missing required figure: figures/{filename}")
        elif path.suffix == ".png" and path.stat().st_size < 1_000:
            errors.append(f"figure is unexpectedly small: figures/{filename}")

    summary = _load_json(run_dir / "summary.json", errors)
    state = _load_json(run_dir / "state.json", errors)
    if expected_count is None:
        declared_count = state.get("scenario_count", summary.get("scenario_count"))
        if not isinstance(declared_count, int) or declared_count < 1:
            errors.append("suite run does not declare a valid scenario count")
            expected_count = 0
        else:
            expected_count = declared_count
    if summary:
        if summary.get("scenario_count") != expected_count:
            errors.append(f"summary scenario_count must be {expected_count}")
        if summary.get("execution_pass_count") != expected_count:
            errors.append(f"execution_pass_count must be {expected_count}")
        if not summary.get("all_scenarios_executed"):
            errors.append("all_scenarios_executed must be true")
    if state:
        if state.get("status") != "COMPLETE":
            errors.append("state.status must be COMPLETE")
        if len(state.get("scenarios", {})) != expected_count:
            errors.append(f"state must contain {expected_count} scenario records")

    result_path = run_dir / "scenario_results.csv"
    scenario_ids: list[str] = []
    if result_path.is_file():
        with result_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        ids = [row.get("scenario_id") for row in rows]
        scenario_ids = [scenario_id for scenario_id in ids if isinstance(scenario_id, str)]
        if len(scenario_ids) != expected_count or scenario_ids != sorted(scenario_ids):
            errors.append("scenario_results.csv ids must be complete and ordered")
    if not scenario_ids and state:
        scenario_ids = sorted(str(item) for item in state.get("scenarios", {}))
    scenario_root = run_dir / "scenarios"
    for scenario_id in scenario_ids:
        scenario_dir = scenario_root / scenario_id
        for relative in (
            "spec.yaml",
            "descriptor.json",
            "visualization.yaml",
            "replay_index.json",
            "baseline_metrics.json",
            "candidate_metrics.json",
            "comparison.json",
            "policy_binding.json",
        ):
            if not (scenario_dir / relative).is_file():
                errors.append(f"{scenario_id} missing {relative}")
        _validate_visualization_artifacts(scenario_dir, scenario_id, errors)
        _validate_policy_binding(scenario_dir, scenario_id, errors)
    return errors


def _validate_visualization_artifacts(
    scenario_dir: Path,
    scenario_id: str,
    errors: list[str],
) -> None:
    descriptor = _load_json(scenario_dir / "descriptor.json", errors)
    visualization_path = scenario_dir / "visualization.yaml"
    visualization: dict[str, object] = {}
    if visualization_path.is_file():
        try:
            loaded = yaml.safe_load(visualization_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                errors.append(f"{scenario_id} visualization.yaml root must be an object")
            else:
                visualization = loaded
        except Exception as error:
            errors.append(f"{scenario_id} cannot parse visualization.yaml: {error}")
    if visualization:
        errors.extend(
            f"{scenario_id} visualization: {error}"
            for error in validate_visualization_spec(visualization)
        )
    if descriptor and descriptor.get("scenario_id") != scenario_id:
        errors.append(f"{scenario_id} descriptor scenario_id mismatch")
    if descriptor and descriptor.get("visualization") != visualization:
        errors.append(f"{scenario_id} descriptor visualization mismatch")

    replay_index = _load_json(scenario_dir / "replay_index.json", errors)
    if not replay_index:
        return
    if replay_index.get("scenario_id") != scenario_id:
        errors.append(f"{scenario_id} replay index scenario_id mismatch")
    replays = replay_index.get("replays")
    if not isinstance(replays, list):
        errors.append(f"{scenario_id} replay index replays must be a list")
        return
    world = visualization.get("world") if visualization else None
    dimension = world.get("dimension") if isinstance(world, dict) else None
    roles: set[str] = set()
    scenario_root = scenario_dir.resolve()
    for entry in replays:
        if not isinstance(entry, dict):
            errors.append(f"{scenario_id} replay index entry must be an object")
            continue
        role = entry.get("policy_role")
        if isinstance(role, str):
            roles.add(role)
        relative = entry.get("path")
        if not isinstance(relative, str):
            errors.append(f"{scenario_id} replay index entry path must be a string")
            continue
        replay_path = (scenario_dir / relative).resolve()
        if not replay_path.is_relative_to(scenario_root):
            errors.append(f"{scenario_id} replay path escapes scenario directory: {relative}")
            continue
        replay = _load_json(replay_path, errors)
        if not replay:
            continue
        if replay.get("schema_version") not in {"scenario_replay/v1", "scenario_replay/v2"}:
            errors.append(f"{scenario_id} unsupported replay schema")
        if replay.get("policy_id") != entry.get("policy_id"):
            errors.append(f"{scenario_id} replay index policy_id mismatch")
        frames = replay.get("frames")
        if not isinstance(frames, list):
            errors.append(f"{scenario_id} replay frames must be a list")
            continue
        if entry.get("frame_count") != len(frames):
            errors.append(f"{scenario_id} replay frame_count mismatch")
        _validate_frames(frames, scenario_id, dimension, errors)
    if roles != {"baseline", "candidate"}:
        errors.append(f"{scenario_id} replay index must contain baseline and candidate")


def _validate_frames(
    frames: list[object],
    scenario_id: str,
    dimension: object,
    errors: list[str],
) -> None:
    for frame_index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            errors.append(f"{scenario_id} frame {frame_index} must be an object")
            continue
        entities = frame.get("entities", [])
        if not isinstance(entities, list):
            errors.append(f"{scenario_id} frame {frame_index} entities must be a list")
            continue
        entity_ids = [entity.get("id") for entity in entities if isinstance(entity, dict)]
        if len(entity_ids) != len(set(entity_ids)):
            errors.append(f"{scenario_id} frame {frame_index} entity ids must be unique")
        if not isinstance(dimension, int):
            continue
        for entity in entities:
            position = entity.get("position") if isinstance(entity, dict) else None
            if not isinstance(position, list) or len(position) != dimension:
                errors.append(
                    f"{scenario_id} frame {frame_index} entity position dimension mismatch"
                )
                break


def _validate_policy_binding(
    scenario_dir: Path,
    scenario_id: str,
    errors: list[str],
) -> None:
    binding = _load_json(scenario_dir / "policy_binding.json", errors)
    comparison = _load_json(scenario_dir / "comparison.json", errors)
    if not binding or not comparison:
        return
    policies = binding.get("policies", {})
    if not isinstance(policies, dict):
        errors.append(f"{scenario_id} policy_binding.policies must be an object")
        return
    replay_index = _load_json(scenario_dir / "replay_index.json", errors)
    indexed_replays = replay_index.get("replays", []) if replay_index else []
    if not isinstance(indexed_replays, list):
        indexed_replays = []
    scenario_root = scenario_dir.resolve()
    for role in ("baseline", "candidate"):
        policy = policies.get(role)
        if not isinstance(policy, dict):
            errors.append(f"{scenario_id} missing {role} policy binding")
            continue
        policy_id = policy.get("policy_id")
        if comparison.get(f"{role}_policy_id") != policy_id:
            errors.append(f"{scenario_id} {role} comparison policy_id mismatch")
        freeze_hash = policy.get("freeze_hash")
        if not isinstance(freeze_hash, str) or len(freeze_hash) != 64:
            errors.append(f"{scenario_id} {role} freeze_hash is invalid")
        role_replays = [
            entry
            for entry in indexed_replays
            if isinstance(entry, dict) and entry.get("policy_role") == role
        ]
        if not role_replays:
            errors.append(f"{scenario_id} missing indexed {role} replay")
            continue
        for entry in role_replays:
            relative = entry.get("path")
            if not isinstance(relative, str):
                continue
            replay_path = (scenario_dir / relative).resolve()
            if not replay_path.is_relative_to(scenario_root):
                continue
            replay = _load_json(replay_path, errors)
            if replay and replay.get("policy_id") != policy_id:
                errors.append(f"{scenario_id} {role} replay policy_id mismatch")


def _load_json(path: Path, errors: list[str]) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        errors.append(f"cannot parse {path.name}: {error}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.name} root must be an object")
        return {}
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a scenario suite run.")
    parser.add_argument("--suite-run", required=True)
    args = parser.parse_args()
    errors = validate_suite_run(Path(args.suite_run))
    if errors:
        print("suite validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("suite validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
