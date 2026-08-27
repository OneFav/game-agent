from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from game_agent.utils.fs import read_json, read_yaml


_SCENARIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RepositoryError(ValueError):
    """Raised when a requested visualization artifact is invalid or unavailable."""


class RunRepository:
    """Read-only access to one suite run, constrained to its resolved root."""

    def __init__(self, project_root: Path, run_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        requested = Path(run_root)
        if not requested.is_absolute():
            requested = self.project_root / requested
        self.run_root = requested.resolve()
        if not self.run_root.is_dir():
            raise RepositoryError(f"suite run directory does not exist: {self.run_root}")
        self.scenario_root = self._within(self.run_root / "scenarios")
        if not self.scenario_root.is_dir():
            raise RepositoryError("suite run does not contain a scenarios directory")

    def list_scenarios(self) -> list[dict[str, Any]]:
        run_state = self._load_optional_json(self.run_root / "state.json")
        state_scenarios = run_state.get("scenarios", {})
        if not isinstance(state_scenarios, dict):
            state_scenarios = {}
        summaries: list[dict[str, Any]] = []
        for scenario_dir in sorted(self.scenario_root.iterdir(), key=lambda path: path.name):
            if not scenario_dir.is_dir() or not _SCENARIO_ID.fullmatch(scenario_dir.name):
                continue
            spec = self._load_optional_yaml(scenario_dir / "spec.yaml")
            descriptor = self._load_optional_json(scenario_dir / "descriptor.json")
            replay_index = self.load_replay_index(scenario_dir.name)
            descriptor_visualization = descriptor.get("visualization")
            if not isinstance(descriptor_visualization, dict):
                descriptor_visualization = {}
            result = state_scenarios.get(scenario_dir.name, {})
            if not isinstance(result, dict):
                result = {}
            summaries.append(
                {
                    "scenario_id": scenario_dir.name,
                    "name": spec.get("name", scenario_dir.name),
                    "task_family": descriptor.get(
                        "task_family", spec.get("task_family", "unknown")
                    ),
                    "dimension": descriptor_visualization
                    .get("world", {})
                    .get("dimension", spec.get("runtime_config", {}).get("dimension", 2)),
                    "replay_count": len(replay_index.get("replays", [])),
                    "capabilities": descriptor.get("capabilities", spec.get("capabilities", {})),
                    "baseline_mean": result.get("baseline_mean"),
                    "candidate_mean": result.get("candidate_mean"),
                    "delta": result.get("delta"),
                    "primary_metric": result.get("primary_metric"),
                    "constraints_passed": result.get("constraints_passed"),
                    "promoted": result.get("promoted"),
                    "result_status": result.get("status"),
                    "attention": result.get("constraints_passed") is False
                    or result.get("status") in {"ERROR", "FAIL_STOP"},
                    "source_kind": "scenario",
                    "group_id": run_state.get("suite_id", self.run_root.name),
                }
            )
        return summaries

    def load_project(self, scenario_id: str) -> dict[str, Any]:
        scenario_dir = self._scenario_dir(scenario_id)
        summary = next(
            (item for item in self.list_scenarios() if item["scenario_id"] == scenario_id),
            None,
        )
        if summary is None:
            raise RepositoryError(f"unknown scenario: {scenario_id}")
        comparison = self._load_optional_json(scenario_dir / "comparison.json")
        binding = self._load_optional_json(scenario_dir / "policy_binding.json")
        candidate_metrics = self._load_optional_json(
            scenario_dir / "candidate_metrics.json"
        )
        policies = binding.get("policies", {})
        if not isinstance(policies, dict):
            policies = {}
        candidate = policies.get("candidate", {})
        if not isinstance(candidate, dict):
            candidate = {}
        method = candidate.get("method", {})
        if not isinstance(method, dict):
            method = {}
        primary_metric = comparison.get("primary_metric") or summary.get("primary_metric")
        constraints_passed = comparison.get(
            "constraints_passed", summary.get("constraints_passed")
        )
        return {
            "schema_version": "autogame_project/v1",
            "project_id": scenario_id,
            "scenario_id": scenario_id,
            "title": f"{scenario_id} {summary['name']}",
            "name": summary["name"],
            "source_kind": "scenario",
            "group_id": summary.get("group_id"),
            "execution_mode": "autonomous",
            "status": "attention" if summary.get("attention") else "complete",
            "attention": summary.get("attention", False),
            "task_family": summary.get("task_family"),
            "dimension": summary.get("dimension"),
            "primary_metric": primary_metric,
            "comparison": comparison,
            "method": {
                "name": method.get("name")
                or comparison.get("candidate_policy_id")
                or "candidate",
                "family": method.get("family", "unknown"),
                "algorithm_family": method.get("algorithm_family"),
                "selection_rationale": method.get("selection_rationale"),
                "policy_id": comparison.get("candidate_policy_id"),
            },
            "workflow": self._derive_workflow(scenario_dir, constraints_passed),
            "metric_series": self._metric_series(scenario_id, primary_metric),
            "constraint_evidence": _constraint_evidence(
                candidate_metrics, constraints_passed
            ),
            "available_interventions": [
                "change_method",
                "adjust_budget",
                "rerun",
                "pause",
                "stop",
                "message",
            ],
        }

    def load_descriptor(self, scenario_id: str) -> dict[str, Any]:
        scenario_dir = self._scenario_dir(scenario_id)
        path = scenario_dir / "descriptor.json"
        if path.is_file():
            return read_json(path)
        return self._legacy_descriptor(scenario_id, scenario_dir)

    def load_visualization(self, scenario_id: str) -> dict[str, Any]:
        scenario_dir = self._scenario_dir(scenario_id)
        path = scenario_dir / "visualization.yaml"
        if path.is_file():
            return read_yaml(path)
        descriptor = self.load_descriptor(scenario_id)
        visualization = descriptor.get("visualization")
        if isinstance(visualization, dict):
            return visualization
        return self._legacy_visualization(scenario_dir)

    def load_replay_index(self, scenario_id: str) -> dict[str, Any]:
        scenario_dir = self._scenario_dir(scenario_id)
        path = scenario_dir / "replay_index.json"
        if path.is_file():
            index = read_json(path)
            self._validate_replay_paths(scenario_dir, index)
            return index
        return self._legacy_replay_index(scenario_id, scenario_dir)

    def load_replay(
        self,
        scenario_id: str,
        policy_role: str,
        seed: int,
    ) -> dict[str, Any]:
        scenario_dir = self._scenario_dir(scenario_id)
        index = self.load_replay_index(scenario_id)
        for entry in index.get("replays", []):
            if entry.get("policy_role", entry.get("policy")) != policy_role:
                continue
            if int(entry.get("seed", -1)) != int(seed):
                continue
            relative = entry.get("path")
            if not isinstance(relative, str):
                raise RepositoryError("replay index path must be a string")
            replay_path = self._within(scenario_dir / relative, parent=scenario_dir)
            if not replay_path.is_file():
                raise RepositoryError(f"replay does not exist: {relative}")
            return read_json(replay_path)
        raise RepositoryError(
            f"replay not found for scenario={scenario_id}, role={policy_role}, seed={seed}"
        )

    def load_frames(
        self,
        scenario_id: str,
        policy_role: str,
        seed: int,
        *,
        start: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        if start < 0:
            raise RepositoryError("start must be non-negative")
        if limit < 1 or limit > 2_000:
            raise RepositoryError("limit must be between 1 and 2000")
        replay = self.load_replay(scenario_id, policy_role, seed)
        frames = replay.get("frames", [])
        if not isinstance(frames, list):
            raise RepositoryError("replay frames must be a list")
        return {
            "schema_version": "scenario_frame_page/v1",
            "scenario_id": scenario_id,
            "policy_role": policy_role,
            "policy_id": replay.get("policy_id"),
            "seed": int(seed),
            "start": start,
            "limit": limit,
            "total": len(frames),
            "frames": frames[start : start + limit],
            "events": replay.get("events", []),
            "metrics": replay.get("metrics", {}),
            "disclosures": replay.get("disclosures", []),
        }

    def _scenario_dir(self, scenario_id: str) -> Path:
        if not isinstance(scenario_id, str) or not _SCENARIO_ID.fullmatch(scenario_id):
            raise RepositoryError("invalid scenario id")
        scenario_dir = self._within(self.scenario_root / scenario_id, parent=self.scenario_root)
        if not scenario_dir.is_dir():
            raise RepositoryError(f"unknown scenario: {scenario_id}")
        return scenario_dir

    def _derive_workflow(
        self, scenario_dir: Path, constraints_passed: Any
    ) -> list[dict[str, str]]:
        nodes = [
            ("read", "读取场景", (scenario_dir / "descriptor.json").is_file()),
            ("baseline", "Baseline", (scenario_dir / "baseline_metrics.json").is_file()),
            ("candidate", "Candidate", (scenario_dir / "candidate_metrics.json").is_file()),
            ("constraints", "约束检查", (scenario_dir / "comparison.json").is_file()),
            ("analysis", "差异分析", (scenario_dir / "comparison.json").is_file()),
        ]
        workflow: list[dict[str, str]] = []
        for node_id, label, complete in nodes:
            status = "complete" if complete else "pending"
            if node_id == "constraints" and constraints_passed is False:
                status = "attention"
            workflow.append({"id": node_id, "label": label, "status": status})
        first_pending = next(
            (node for node in workflow if node["status"] == "pending"), None
        )
        if first_pending is not None:
            first_pending["status"] = "active"
        return workflow

    def _metric_series(
        self, scenario_id: str, primary_metric: Any
    ) -> dict[str, list[dict[str, float]]]:
        result: dict[str, list[dict[str, float]]] = {}
        index = self.load_replay_index(scenario_id)
        for role in ("baseline", "candidate"):
            replay_entry = next(
                (
                    item
                    for item in index.get("replays", [])
                    if item.get("policy_role", item.get("policy")) == role
                    and int(item.get("seed", 0)) == 0
                ),
                None,
            )
            if replay_entry is None:
                continue
            replay = self.load_replay(scenario_id, role, 0)
            points: list[dict[str, float]] = []
            for frame in replay.get("frames", []):
                if not isinstance(frame, dict):
                    continue
                metrics = frame.get("metrics", {})
                if not isinstance(metrics, dict):
                    metrics = {}
                value = metrics.get(primary_metric) if isinstance(primary_metric, str) else None
                if not isinstance(value, (int, float)):
                    value = metrics.get(
                        "primary_value", metrics.get("task_progress", metrics.get("progress"))
                    )
                if isinstance(value, (int, float)):
                    points.append(
                        {
                            "step": float(frame.get("episode_step", len(points))),
                            "time": float(frame.get("scenario_time", len(points))),
                            "value": float(value),
                        }
                    )
            result[role] = points
        return result

    def _within(self, path: Path, *, parent: Path | None = None) -> Path:
        root = (parent or self.run_root).resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise RepositoryError(f"path escapes suite run boundary: {path}")
        return resolved

    def _validate_replay_paths(
        self, scenario_dir: Path, replay_index: dict[str, Any]
    ) -> None:
        replays = replay_index.get("replays")
        if not isinstance(replays, list):
            raise RepositoryError("replay index must contain a replay list")
        for entry in replays:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise RepositoryError("replay index entries require a path")
            self._within(scenario_dir / entry["path"], parent=scenario_dir)

    def _legacy_replay_index(
        self, scenario_id: str, scenario_dir: Path
    ) -> dict[str, Any]:
        replays: list[dict[str, Any]] = []
        replay_dir = scenario_dir / "replays"
        if replay_dir.is_dir():
            for replay_path in sorted(replay_dir.glob("*_seed_*.json")):
                replay_path = self._within(replay_path, parent=scenario_dir)
                replay = read_json(replay_path)
                frames = replay.get("frames", [])
                replays.append(
                    {
                        "policy_role": replay.get("policy", replay_path.stem.split("_seed_")[0]),
                        "policy_id": replay.get("policy_id"),
                        "seed": int(replay.get("seed", 0)),
                        "path": replay_path.relative_to(scenario_dir).as_posix(),
                        "frame_count": len(frames) if isinstance(frames, list) else 0,
                        "duration": _replay_duration(frames),
                    }
                )
        return {
            "schema_version": "scenario_replay_index/v0-fallback",
            "scenario_id": scenario_id,
            "descriptor": "descriptor.json",
            "visualization": "visualization.yaml",
            "replays": replays,
            "disclosures": ["由 legacy scenario_replay/v1 文件动态构建索引。"],
        }

    def _legacy_descriptor(
        self, scenario_id: str, scenario_dir: Path
    ) -> dict[str, Any]:
        spec = self._load_optional_yaml(scenario_dir / "spec.yaml")
        visualization = self._legacy_visualization(scenario_dir)
        return {
            "scenario_id": scenario_id,
            "task_family": spec.get("task_family", "unknown"),
            "capabilities": spec.get("capabilities", {}),
            "agents": [],
            "observation_spaces": {},
            "action_spaces": {},
            "disclosures": [
                *spec.get("disclosures", []),
                "该 descriptor 由旧版 suite 产物兼容生成。",
            ],
            "visualization": visualization,
        }

    def _legacy_visualization(self, scenario_dir: Path) -> dict[str, Any]:
        spec = self._load_optional_yaml(scenario_dir / "spec.yaml")
        runtime_config = spec.get("runtime_config", {})
        dimension = int(runtime_config.get("dimension", 2))
        boundary = float(runtime_config.get("boundary", 10.0))
        layer_ids = ("entities", "goals", "trajectories", "relations", "fields", "events")
        kinds = ("entity_markers", "goal_markers", "trajectories", "relations", "vector_fields", "events")
        sources = ("entities", "entities", "entities", "relations", "fields", "events")
        return {
            "schema_version": "scenario_visualization/v0-fallback",
            "world": {
                "dimension": dimension,
                "bounds": {
                    "minimum": [-boundary] * dimension,
                    "maximum": [boundary] * dimension,
                },
                "units": "abstract",
                "axis_labels": ["x", "y", "z"][:dimension],
            },
            "static_primitives": [
                {
                    "id": "world_boundary",
                    "kind": "boundary_box",
                    "label": "World boundary",
                    "points": [],
                    "center": [0.0] * dimension,
                    "radius": None,
                    "style": {},
                    "metadata": {
                        "minimum": [-boundary] * dimension,
                        "maximum": [boundary] * dimension,
                    },
                }
            ],
            "dynamic_layers": [
                {
                    "id": layer_id,
                    "kind": kind,
                    "source": source,
                    "label": layer_id.replace("_", " ").title(),
                    "attribute": "goal" if layer_id == "goals" else None,
                    "enabled_by_default": True,
                    "style": {},
                }
                for layer_id, kind, source in zip(layer_ids, kinds, sources)
            ],
            "views": [
                {
                    "id": "default",
                    "projection": "2d" if dimension == 2 else "3d",
                    "label": "Default overview",
                    "layer_ids": ["world_boundary", *layer_ids],
                    "camera": {"fit": "bounds"},
                }
            ],
            "disclosures": ["使用 legacy replay 的通用图层回退，不代表高保真几何。"],
        }

    @staticmethod
    def _load_optional_json(path: Path) -> dict[str, Any]:
        return read_json(path) if path.is_file() else {}

    @staticmethod
    def _load_optional_yaml(path: Path) -> dict[str, Any]:
        return read_yaml(path) if path.is_file() else {}


def _replay_duration(frames: Any) -> float:
    if not isinstance(frames, list) or not frames:
        return 0.0
    first = frames[0] if isinstance(frames[0], dict) else {}
    last = frames[-1] if isinstance(frames[-1], dict) else {}
    return max(
        0.0,
        float(last.get("scenario_time", 0.0))
        - float(first.get("scenario_time", 0.0)),
    )


def _constraint_evidence(
    metrics: dict[str, Any], constraints_passed: Any
) -> list[dict[str, Any]]:
    if constraints_passed is not False:
        return []
    statistics = metrics.get("statistics", {})
    if not isinstance(statistics, dict):
        statistics = {}
    per_seed = metrics.get("per_seed", [])
    if not isinstance(per_seed, list):
        per_seed = []
    candidates = (
        ("collision_count", "平均碰撞次数", 0.0),
        ("collision_rate", "碰撞率", 0.0),
        ("out_of_bounds_rate", "越界率", 0.0),
        ("action_violation_rate", "动作违规率", 0.0),
    )
    evidence: list[dict[str, Any]] = []
    for key, label, limit in candidates:
        stat = statistics.get(key, {})
        if not isinstance(stat, dict):
            continue
        value = stat.get("mean")
        if isinstance(value, (int, float)) and float(value) > limit:
            failing_seed = next(
                (
                    index
                    for index, item in enumerate(per_seed)
                    if isinstance(item, dict)
                    and isinstance(item.get(key), (int, float))
                    and float(item[key]) > limit
                ),
                None,
            )
            evidence.append(
                {
                    "metric": key,
                    "label": label,
                    "value": float(value),
                    "limit": limit,
                    "seed": failing_seed,
                }
            )
    if evidence:
        return evidence
    return [
        {
            "metric": "constraints_passed",
            "label": "约束检查",
            "value": False,
            "limit": True,
        }
    ]
