from __future__ import annotations

from pathlib import Path

import pytest

from game_agent.utils.fs import write_json, write_yaml
from game_agent.visualization.repository import RepositoryError, RunRepository


def test_run_repository_lists_and_pages_replay_frames(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    repository = RunRepository(tmp_path, run_dir)

    assert repository.list_scenarios()[0]["scenario_id"] == "S01"
    assert repository.load_descriptor("S01")["scenario_id"] == "S01"
    page = repository.load_frames("S01", "candidate", 0, start=1, limit=1)
    assert page["total"] == 2
    assert page["start"] == 1
    assert page["frames"][0]["episode_step"] == 4


def test_run_repository_maps_scenario_to_workbench_project(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    repository = RunRepository(tmp_path, run_dir)

    project = repository.load_project("S01")

    assert project["project_id"] == "S01"
    assert project["execution_mode"] == "autonomous"
    assert project["workflow"][0]["label"] == "读取场景"
    assert project["metric_series"]["candidate"][-1]["value"] == 0.5


def test_run_repository_rejects_paths_outside_declared_boundaries(
    tmp_path: Path,
) -> None:
    run_dir = _write_run(tmp_path)
    archived_repository = RunRepository(tmp_path / "separate_project", run_dir)
    assert archived_repository.list_scenarios()[0]["scenario_id"] == "S01"

    repository = RunRepository(tmp_path, run_dir)
    with pytest.raises(RepositoryError, match="invalid scenario id"):
        repository.load_descriptor("../S01")

    index_path = run_dir / "scenarios" / "S01" / "replay_index.json"
    index = repository.load_replay_index("S01")
    index["replays"][0]["path"] = "../../../outside.json"
    write_json(index_path, index)
    with pytest.raises(RepositoryError, match="escapes"):
        repository.load_replay_index("S01")


def _write_run(project_root: Path) -> Path:
    run_dir = project_root / "suite_runs" / "sample"
    scenario_dir = run_dir / "scenarios" / "S01"
    visualization = {
        "schema_version": "scenario_visualization/v1",
        "world": {
            "dimension": 2,
            "bounds": {
                "minimum": [-10.0, -10.0],
                "maximum": [10.0, 10.0],
            },
            "units": "abstract",
            "axis_labels": ["x", "y"],
        },
        "static_primitives": [],
        "dynamic_layers": [
            {
                "id": "entities",
                "kind": "entity_markers",
                "source": "entities",
                "label": "Entities",
                "attribute": None,
                "enabled_by_default": True,
                "style": {},
            }
        ],
        "views": [
            {
                "id": "default",
                "projection": "2d",
                "label": "Default",
                "layer_ids": ["entities"],
                "camera": {},
            }
        ],
        "disclosures": [],
    }
    write_yaml(
        scenario_dir / "spec.yaml",
        {
            "scenario_id": "S01",
            "name": "二维到达",
            "task_family": "navigation",
            "runtime_config": {"dimension": 2, "boundary": 10.0},
        },
    )
    write_json(
        scenario_dir / "descriptor.json",
        {
            "scenario_id": "S01",
            "task_family": "navigation",
            "capabilities": {},
            "agents": ["red_0"],
            "observation_spaces": {},
            "action_spaces": {},
            "disclosures": [],
            "visualization": visualization,
        },
    )
    write_yaml(scenario_dir / "visualization.yaml", visualization)
    frames = [
        {
            "scenario_time": 0.0,
            "episode_step": 0,
            "entities": [{"id": "red_0", "position": [0.0, 0.0]}],
            "relations": [],
            "fields": [],
            "events": [],
            "metrics": {},
        },
        {
            "scenario_time": 0.4,
            "episode_step": 4,
            "entities": [{"id": "red_0", "position": [1.0, 1.0]}],
            "relations": [],
            "fields": [],
            "events": [],
            "metrics": {"progress": 0.5},
        },
    ]
    write_json(
        scenario_dir / "replays" / "candidate_seed_0.json",
        {
            "schema_version": "scenario_replay/v2",
            "scenario_id": "S01",
            "seed": 0,
            "policy": "candidate",
            "policy_id": "sample_policy",
            "frames": frames,
            "events": [],
            "metrics": {"progress": 0.5},
            "disclosures": [],
        },
    )
    write_json(
        scenario_dir / "replay_index.json",
        {
            "schema_version": "scenario_replay_index/v1",
            "scenario_id": "S01",
            "descriptor": "descriptor.json",
            "visualization": "visualization.yaml",
            "replays": [
                {
                    "policy_role": "candidate",
                    "policy_id": "sample_policy",
                    "seed": 0,
                    "path": "replays/candidate_seed_0.json",
                    "frame_count": 2,
                    "duration": 0.4,
                }
            ],
        },
    )
    return run_dir
