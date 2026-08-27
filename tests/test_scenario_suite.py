from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from contracts.runtime_protocol import ScenarioRuntime
from game_agent.autoresearch.suite_runner import ScenarioSuiteRunner, load_suite
from game_agent.scenarios import (
    CAPABILITY_COLUMNS,
    build_max_space_50_catalog,
    catalog_by_id,
    create_runtime,
)
from game_agent.utils.fs import write_yaml
from game_agent.utils.policy_loader import load_policy
from game_agent.visualization import validate_visualization_spec
from hooks.post_suite_run import validate_suite_run


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_catalog_contains_exactly_fifty_distinct_tasks() -> None:
    catalog = build_max_space_50_catalog()

    assert len(catalog) == 50
    assert [item["scenario_id"] for item in catalog] == [
        f"S{index:02d}" for index in range(1, 51)
    ]
    assert len({item["representative_distinction"] for item in catalog}) == 50
    assert len({item["primary_metric"] for item in catalog}) == 50
    assert all(set(CAPABILITY_COLUMNS) <= set(item["capabilities"]) for item in catalog)


def test_checked_in_suite_selects_all_catalog_entries() -> None:
    suite, specs = load_suite(ROOT / "suites" / "max_space_50_v1" / "suite.yaml")

    assert suite["suite_id"] == "max_space_50_v1"
    assert len(specs) == 50


def test_legacy_drone_ring_is_adapted_to_runtime_protocol() -> None:
    runtime = create_runtime(
        {"task_id": "legacy_test", "task_family": "drone_ring_game", "env_config": {}}
    )

    assert isinstance(runtime, ScenarioRuntime)
    runtime.reset(seed=0)
    assert runtime.snapshot().entities
    runtime.close()


def test_reference_runtime_is_seed_deterministic() -> None:
    spec = catalog_by_id()["S39"]
    first = _rollout(spec, seed=7)
    second = _rollout(spec, seed=7)

    assert first == second


def test_every_scenario_loads_an_explicit_bounded_policy_package() -> None:
    baseline_ids: set[str] = set()
    for spec in build_max_space_50_catalog():
        runtime = create_runtime(spec)
        descriptor = runtime.describe()
        agent = descriptor.agents[0]
        env_spec = {
            "scenario_id": spec["scenario_id"],
            "task_family": spec["task_family"],
            "scenario": spec,
            "action_space": descriptor.action_spaces[agent],
            "observation_space": descriptor.observation_spaces[agent],
        }
        observations, info = runtime.reset(seed=0)
        policy_id = spec["candidate_policy_id"]
        policy, _ = load_policy(ROOT / "policies" / policy_id, env_spec)
        policy.reset(0)
        action = np.asarray(policy.act(observations, agent, info), dtype=np.float32)
        assert action.shape == runtime.action_shape
        assert np.all(np.isfinite(action))
        assert np.all(action >= runtime.action_low)
        assert np.all(action <= runtime.action_high)
        baseline_ids.add(spec["baseline_policy_id"])
        runtime.close()

    assert baseline_ids == {"max_space_zero_v1"}


def test_runtime_exposes_graph_image_and_lifecycle_contracts() -> None:
    graph_runtime = create_runtime(catalog_by_id()["S48"])
    graph_observations, _ = graph_runtime.reset(seed=0)
    graph_sample = next(iter(graph_observations.values()))
    assert {"graph", "proprioception"} <= set(graph_sample)
    assert {"nodes", "edges", "edge_features"} <= set(graph_sample["graph"])
    graph_runtime.close()

    image_runtime = create_runtime(catalog_by_id()["S49"])
    image_observations, _ = image_runtime.reset(seed=0)
    image_sample = next(iter(image_observations.values()))
    assert image_sample["depth_image"].shape == (8, 8, 1)
    image_runtime.close()

    lifecycle_runtime = create_runtime(catalog_by_id()["S41"])
    lifecycle_runtime.reset(seed=0)
    initial_agents = len(lifecycle_runtime.agents)
    event_types: set[str] = set()
    for _ in range(lifecycle_runtime.max_steps // 3):
        result = lifecycle_runtime.step(
            {
                agent: np.zeros(lifecycle_runtime.action_shape, dtype=np.float32)
                for agent in lifecycle_runtime.agents
            }
        )
        event_types.update(event["event_type"] for event in result[4]["events"])
    assert initial_agents == 2
    assert len(lifecycle_runtime.agents) == 4
    assert "entity_spawned" in event_types
    lifecycle_runtime.close()


def test_visualization_contract_covers_key_scene_shapes_and_layers() -> None:
    expectations = {
        "S01": (2, "entity_markers", 1),
        "S31": (2, "relations", 2),
        "S39": (3, "vector_fields", 1),
        "S41": (2, "events", 4),
        "S47": (2, "trajectories", 50),
    }
    for scenario_id, (dimension, layer_kind, entity_count) in expectations.items():
        runtime = create_runtime(catalog_by_id()[scenario_id])
        descriptor = runtime.describe()
        assert descriptor.visualization is not None
        assert validate_visualization_spec(descriptor.visualization) == []
        assert descriptor.visualization.world.dimension == dimension
        assert layer_kind in {
            layer.kind for layer in descriptor.visualization.dynamic_layers
        }
        runtime.reset(seed=0)
        frame = runtime.snapshot()
        assert len(frame.entities) == entity_count
        if scenario_id == "S31":
            assert frame.relations
        if scenario_id == "S39":
            assert frame.fields
        if scenario_id == "S41":
            assert frame.events
        runtime.close()


def test_suite_runner_writes_isolated_resumable_evidence(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.yaml"
    output_dir = tmp_path / "run"
    write_yaml(
        suite_path,
        {
            "schema_version": "scenario_suite/v1",
            "suite_id": "test_subset",
            "catalog": "max_space_50_v1",
            "seeds": [3, 5],
            "budget": {"max_steps": 12, "replay_interval": 3},
            "scenarios": ["S01", "S31", "S49"],
        },
    )

    runner = ScenarioSuiteRunner(ROOT)
    runner.run(suite_path, output_dir)
    state_before = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))
    runner.run(suite_path, output_dir, resume=True)
    state_after = json.loads((output_dir / "state.json").read_text(encoding="utf-8"))

    assert state_before["status"] == "COMPLETE"
    assert state_after["status"] == "COMPLETE"
    assert set(state_after["scenarios"]) == {"S01", "S31", "S49"}
    assert (output_dir / "scenario_results.csv").is_file()
    assert (output_dir / "figures" / "scenario_results_overview.png").stat().st_size > 1_000
    assert validate_suite_run(output_dir, expected_count=3) == []
    for scenario_id in ("S01", "S31", "S49"):
        scenario_dir = output_dir / "scenarios" / scenario_id
        assert (scenario_dir / "spec.yaml").is_file()
        assert (scenario_dir / "descriptor.json").is_file()
        assert (scenario_dir / "visualization.yaml").is_file()
        assert (scenario_dir / "replay_index.json").is_file()
        assert (scenario_dir / "comparison.json").is_file()
        replay_path = scenario_dir / "replays" / "candidate_seed_3.json"
        assert replay_path.is_file()
        assert (scenario_dir / "replays" / "candidate_seed_5.json").is_file()
        replay_index = json.loads(
            (scenario_dir / "replay_index.json").read_text(encoding="utf-8")
        )
        assert {(entry["policy_role"], entry["seed"]) for entry in replay_index["replays"]} == {
            ("baseline", 3),
            ("baseline", 5),
            ("candidate", 3),
            ("candidate", 5),
        }
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        assert replay["schema_version"] == "scenario_replay/v2"
        assert replay["descriptor_ref"] == "../descriptor.json"


def _rollout(spec: dict[str, object], seed: int) -> dict[str, object]:
    runtime = create_runtime(spec)
    descriptor = runtime.describe()
    agent = descriptor.agents[0]
    env_spec = {
        "scenario_id": spec["scenario_id"],
        "task_family": spec["task_family"],
        "scenario": spec,
        "action_space": descriptor.action_spaces[agent],
        "observation_space": descriptor.observation_spaces[agent],
    }
    policy, _ = load_policy(
        ROOT / "policies" / str(spec["candidate_policy_id"]), env_spec
    )
    policy.reset(seed)
    observations, info = runtime.reset(seed=seed)
    for _ in range(10):
        actions = {
            agent_id: policy.act(observations, agent_id, info)
            for agent_id in runtime.agents
        }
        observations, _, _, _, info = runtime.step(actions)
    result = {
        "metrics": runtime.get_metrics(),
        "snapshot": asdict(runtime.snapshot()),
    }
    runtime.close()
    return _normalize(result)


def _normalize(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value
