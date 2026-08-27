from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


VISUALIZATION_SCHEMA_VERSION = "scenario_visualization/v1"
LAYER_SOURCE_ALLOWLIST = ("entities", "relations", "fields", "events", "messages")
STATIC_PRIMITIVE_KINDS = ("boundary_box", "ring", "polyline", "point")
DYNAMIC_LAYER_KINDS = (
    "entity_markers",
    "goal_markers",
    "trajectories",
    "relations",
    "vector_fields",
    "events",
    "messages",
)
VIEW_PROJECTIONS = ("2d", "3d")

LayerSource = Literal["entities", "relations", "fields", "events", "messages"]
ViewProjection = Literal["2d", "3d"]


@dataclass(frozen=True)
class AxisAlignedBounds:
    """World-space bounds shared by runtime, replay, and viewer."""

    minimum: tuple[float, ...]
    maximum: tuple[float, ...]


@dataclass(frozen=True)
class WorldSpec:
    """Static world metadata required to render a scenario safely."""

    dimension: int
    bounds: AxisAlignedBounds
    units: str = "abstract"
    axis_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class StaticPrimitive:
    """Renderer-independent geometry known before replay frames are loaded."""

    id: str
    kind: str
    label: str
    points: tuple[tuple[float, ...], ...] = ()
    center: tuple[float, ...] | None = None
    radius: float | None = None
    style: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DynamicLayerSpec:
    """Declarative mapping from replay packet fields to viewer layers."""

    id: str
    kind: str
    source: LayerSource
    label: str
    attribute: str | None = None
    style: dict[str, Any] = field(default_factory=dict)
    enabled_by_default: bool = True


@dataclass(frozen=True)
class ViewSpec:
    """Saved viewer preset for one world projection."""

    id: str
    projection: ViewProjection
    label: str
    layer_ids: tuple[str, ...]
    camera: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisualizationSpec:
    """Versioned visualization declaration attached to a scenario descriptor."""

    world: WorldSpec
    static_primitives: tuple[StaticPrimitive, ...] = ()
    dynamic_layers: tuple[DynamicLayerSpec, ...] = ()
    views: tuple[ViewSpec, ...] = ()
    disclosures: tuple[str, ...] = ()
    schema_version: str = VISUALIZATION_SCHEMA_VERSION
