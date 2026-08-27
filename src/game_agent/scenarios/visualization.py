from __future__ import annotations

from typing import Iterable

import numpy as np

from contracts.visualization_protocol import (
    AxisAlignedBounds,
    DynamicLayerSpec,
    StaticPrimitive,
    ViewSpec,
    VisualizationSpec,
    WorldSpec,
)


def build_representative_visualization(
    *,
    dimension: int,
    boundary: float,
    vector_field: bool,
    include_messages: bool,
    disclosures: Iterable[str] = (),
) -> VisualizationSpec:
    bounds = make_world_bounds(dimension=dimension, boundary=boundary)
    layer_ids = ["world_bounds", "entities", "goals", "trajectories", "events"]
    dynamic_layers = [
        DynamicLayerSpec(
            id="entities",
            kind="entity_markers",
            source="entities",
            label="Entities",
            style={"color_by": "team"},
        ),
        DynamicLayerSpec(
            id="goals",
            kind="goal_markers",
            source="entities",
            label="Goals",
            attribute="goal",
            style={"color_by": "team", "marker": "cross"},
        ),
        DynamicLayerSpec(
            id="trajectories",
            kind="trajectories",
            source="entities",
            label="Trajectories",
            style={"position_attribute": "position"},
        ),
        DynamicLayerSpec(
            id="events",
            kind="events",
            source="events",
            label="Events",
        ),
    ]
    if vector_field:
        dynamic_layers.append(
            DynamicLayerSpec(
                id="vector_fields",
                kind="vector_fields",
                source="fields",
                label="Vector fields",
            )
        )
        layer_ids.append("vector_fields")
    if include_messages:
        dynamic_layers.append(
            DynamicLayerSpec(
                id="messages",
                kind="messages",
                source="messages",
                label="Messages",
                enabled_by_default=False,
            )
        )
        layer_ids.append("messages")
    dynamic_layers.append(
        DynamicLayerSpec(
            id="relations",
            kind="relations",
            source="relations",
            label="Relations",
            enabled_by_default=True,
        )
    )
    layer_ids.append("relations")
    views = [
        ViewSpec(
            id="overview_2d",
            projection="2d",
            label="2D overview",
            layer_ids=tuple(layer_ids),
            camera={"fit": "bounds"},
        )
    ]
    if dimension == 3:
        views.append(
            ViewSpec(
                id="overview_3d",
                projection="3d",
                label="3D overview",
                layer_ids=tuple(layer_ids),
                camera={"fit": "bounds", "yaw_degrees": 35.0, "pitch_degrees": 25.0},
            )
        )
    return VisualizationSpec(
        world=WorldSpec(
            dimension=dimension,
            bounds=bounds,
            axis_labels=("x", "y") if dimension == 2 else ("x", "y", "z"),
        ),
        static_primitives=(
            StaticPrimitive(
                id="world_bounds",
                kind="boundary_box",
                label="World bounds",
                center=tuple(0.0 for _ in range(dimension)),
                metadata={
                    "minimum": bounds.minimum,
                    "maximum": bounds.maximum,
                },
            ),
        ),
        dynamic_layers=tuple(dynamic_layers),
        views=tuple(views),
        disclosures=tuple(disclosures),
    )


def build_drone_ring_visualization(
    *,
    boundary: float,
    ring_radius: float,
    rings: Iterable[np.ndarray],
    disclosures: Iterable[str] = (),
) -> VisualizationSpec:
    bounds = make_world_bounds(dimension=2, boundary=boundary)
    static_primitives = [
        StaticPrimitive(
            id="world_bounds",
            kind="boundary_box",
            label="World bounds",
            center=(0.0, 0.0),
            metadata={
                "minimum": bounds.minimum,
                "maximum": bounds.maximum,
            },
        )
    ]
    for index, ring in enumerate(rings):
        center = tuple(np.asarray(ring, dtype=float).tolist())
        static_primitives.append(
            StaticPrimitive(
                id=f"ring_{index:02d}",
                kind="ring",
                label=f"Ring {index + 1}",
                center=center,
                radius=float(ring_radius),
                metadata={"index": index},
            )
        )
    dynamic_layers = (
        DynamicLayerSpec(
            id="entities",
            kind="entity_markers",
            source="entities",
            label="Agents",
            style={"color_by": "id"},
        ),
        DynamicLayerSpec(
            id="trajectories",
            kind="trajectories",
            source="entities",
            label="Trajectories",
            style={"position_attribute": "position"},
        ),
    )
    visible_layers = tuple(
        primitive.id for primitive in static_primitives
    ) + tuple(layer.id for layer in dynamic_layers)
    return VisualizationSpec(
        world=WorldSpec(
            dimension=2,
            bounds=bounds,
            axis_labels=("x", "y"),
        ),
        static_primitives=tuple(static_primitives),
        dynamic_layers=dynamic_layers,
        views=(
            ViewSpec(
                id="overview_2d",
                projection="2d",
                label="2D overview",
                layer_ids=visible_layers,
                camera={"fit": "bounds"},
            ),
        ),
        disclosures=tuple(disclosures),
    )


def make_world_bounds(*, dimension: int, boundary: float) -> AxisAlignedBounds:
    minimum = tuple(float(-boundary) for _ in range(dimension))
    maximum = tuple(float(boundary) for _ in range(dimension))
    return AxisAlignedBounds(minimum=minimum, maximum=maximum)
