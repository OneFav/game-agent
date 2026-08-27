from __future__ import annotations

from dataclasses import replace

from contracts.runtime_protocol import FramePacket
from contracts.visualization_protocol import (
    AxisAlignedBounds,
    DynamicLayerSpec,
    StaticPrimitive,
    ViewSpec,
    VisualizationSpec,
    WorldSpec,
)
from game_agent.scenarios.drone_ring_adapter import DroneRingRuntimeAdapter
from game_agent.scenarios.representative import RepresentativeScenarioRuntime
from game_agent.visualization.validation import (
    validate_frame_packet,
    validate_scenario_descriptor,
    validate_visualization_spec,
    visualization_to_dict,
)


def test_representative_descriptor_exposes_valid_2d_visualization() -> None:
    runtime = RepresentativeScenarioRuntime(
        {
            "scenario_id": "S01",
            "task_family": "representative",
            "runtime_config": {"dimension": 2, "boundary": 3.0},
        }
    )

    descriptor = runtime.describe()

    assert descriptor.visualization is not None
    assert validate_scenario_descriptor(descriptor) == []
    assert descriptor.visualization.world.dimension == 2
    assert {layer.id for layer in descriptor.visualization.dynamic_layers} >= {
        "entities",
        "goals",
        "trajectories",
        "relations",
        "events",
    }


def test_representative_descriptor_exposes_valid_3d_vector_visualization() -> None:
    runtime = RepresentativeScenarioRuntime(
        {
            "scenario_id": "S39",
            "task_family": "representative",
            "runtime_config": {
                "dimension": 3,
                "boundary": 2.5,
                "vector_field": True,
            },
        }
    )

    descriptor = runtime.describe()
    runtime.reset(seed=0)
    frame = runtime.snapshot()

    assert descriptor.visualization is not None
    assert validate_scenario_descriptor(descriptor) == []
    assert validate_frame_packet(frame, descriptor) == []
    assert {view.projection for view in descriptor.visualization.views} == {"2d", "3d"}
    assert {layer.id for layer in descriptor.visualization.dynamic_layers} >= {
        "entities",
        "vector_fields",
    }


def test_drone_ring_descriptor_declares_real_ring_geometry() -> None:
    runtime = DroneRingRuntimeAdapter(
        {
            "task_id": "legacy_test",
            "env_config": {"ring_count": 3, "ring_radius": 0.4, "boundary": 8.0},
        }
    )

    descriptor = runtime.describe()

    assert descriptor.visualization is not None
    assert validate_scenario_descriptor(descriptor) == []
    rings = [item for item in descriptor.visualization.static_primitives if item.kind == "ring"]
    assert len(rings) == 3
    assert [ring.center for ring in rings] == [(2.5, 0.0), (4.5, 0.0), (6.5, 0.0)]
    assert all(ring.radius == 0.4 for ring in rings)


def test_validate_visualization_spec_rejects_invalid_bounds() -> None:
    spec = VisualizationSpec(
        world=WorldSpec(
            dimension=2,
            bounds=AxisAlignedBounds(minimum=(1.0, -1.0), maximum=(1.0, 1.0)),
        ),
        static_primitives=(
            StaticPrimitive(
                id="world_bounds",
                kind="boundary_box",
                label="World bounds",
                center=(0.0, 0.0),
                metadata={"minimum": (1.0, -1.0), "maximum": (1.0, 1.0)},
            ),
        ),
        dynamic_layers=(
            DynamicLayerSpec(
                id="entities",
                kind="entity_markers",
                source="entities",
                label="Entities",
            ),
        ),
        views=(
            ViewSpec(
                id="overview_2d",
                projection="2d",
                label="2D overview",
                layer_ids=("world_bounds", "entities"),
            ),
        ),
    )

    errors = validate_visualization_spec(spec)

    assert "world.bounds axis 0 minimum must be < maximum" in errors


def test_validate_visualization_spec_rejects_invalid_source_and_view_reference() -> None:
    valid_spec = VisualizationSpec(
        world=WorldSpec(
            dimension=2,
            bounds=AxisAlignedBounds(minimum=(-1.0, -1.0), maximum=(1.0, 1.0)),
        ),
        static_primitives=(
            StaticPrimitive(
                id="world_bounds",
                kind="boundary_box",
                label="World bounds",
                center=(0.0, 0.0),
                metadata={"minimum": (-1.0, -1.0), "maximum": (1.0, 1.0)},
            ),
        ),
        dynamic_layers=(
            DynamicLayerSpec(
                id="entities",
                kind="entity_markers",
                source="entities",
                label="Entities",
            ),
        ),
        views=(
            ViewSpec(
                id="overview_2d",
                projection="2d",
                label="2D overview",
                layer_ids=("world_bounds", "entities"),
            ),
        ),
    )
    invalid_spec = replace(
        valid_spec,
        dynamic_layers=(
            DynamicLayerSpec(
                id="entities",
                kind="entity_markers",
                source="fields",
                label="Entities",
            ),
        ),
        views=(
            ViewSpec(
                id="overview_2d",
                projection="2d",
                label="2D overview",
                layer_ids=("world_bounds", "ghost_layer"),
            ),
        ),
    )

    errors = validate_visualization_spec(invalid_spec)

    assert (
        "dynamic layer entities source fields is incompatible with kind entity_markers"
        in errors
    )
    assert "view overview_2d references unknown layer id ghost_layer" in errors


def test_validate_visualization_spec_accepts_mapping_and_normalizes_output() -> None:
    spec = {
        "world": {
            "dimension": 2,
            "bounds": {
                "minimum": [-1.0, -1.0],
                "maximum": [1.0, 1.0],
            },
            "axis_labels": ["x", "y"],
        },
        "static_primitives": [
            {
                "id": "world_bounds",
                "kind": "boundary_box",
                "label": "World bounds",
                "center": [0.0, 0.0],
                "metadata": {
                    "minimum": [-1.0, -1.0],
                    "maximum": [1.0, 1.0],
                },
            }
        ],
        "dynamic_layers": [
            {
                "id": "entities",
                "kind": "entity_markers",
                "source": "entities",
                "label": "Entities",
            }
        ],
        "views": [
            {
                "id": "overview_2d",
                "projection": "2d",
                "label": "2D overview",
                "layer_ids": ["world_bounds", "entities"],
            }
        ],
    }

    assert validate_visualization_spec(spec) == []
    normalized = visualization_to_dict(spec)
    assert normalized["world"]["dimension"] == 2
    assert normalized["views"][0]["layer_ids"] == ["world_bounds", "entities"]


def test_validate_frame_packet_rejects_dimension_mismatch() -> None:
    descriptor = RepresentativeScenarioRuntime(
        {
            "scenario_id": "S39",
            "task_family": "representative",
            "runtime_config": {"dimension": 3},
        }
    ).describe()
    frame = FramePacket(
        scenario_time=0.0,
        episode_step=0,
        entities=(
            {
                "id": "agent_00",
                "position": [0.0, 1.0],
                "velocity": [0.0, 0.0, 0.0],
            },
        ),
    )

    errors = validate_frame_packet(frame, descriptor)

    assert "entity agent_00 position must have length 3" in errors


def test_validate_visualization_spec_rejects_version_and_duplicate_view() -> None:
    runtime = RepresentativeScenarioRuntime(
        {
            "scenario_id": "S01",
            "task_family": "representative",
            "runtime_config": {"dimension": 2},
        }
    )
    visualization = runtime.describe().visualization
    assert visualization is not None
    invalid = replace(
        visualization,
        schema_version="scenario_visualization/v999",
        views=(visualization.views[0], visualization.views[0]),
    )

    errors = validate_visualization_spec(invalid)

    assert "schema_version must be scenario_visualization/v1" in errors
    assert "duplicate view id: overview_2d" in errors
