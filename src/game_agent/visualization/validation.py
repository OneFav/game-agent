from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, Mapping

from contracts.runtime_protocol import FramePacket, ScenarioDescriptor
from contracts.visualization_protocol import (
    DYNAMIC_LAYER_KINDS,
    LAYER_SOURCE_ALLOWLIST,
    STATIC_PRIMITIVE_KINDS,
    VISUALIZATION_SCHEMA_VERSION,
    VIEW_PROJECTIONS,
    AxisAlignedBounds,
    DynamicLayerSpec,
    StaticPrimitive,
    ViewSpec,
    VisualizationSpec,
    WorldSpec,
)

_LAYER_KIND_TO_SOURCES = {
    "entity_markers": {"entities"},
    "goal_markers": {"entities"},
    "trajectories": {"entities"},
    "relations": {"relations"},
    "vector_fields": {"fields"},
    "events": {"events"},
    "messages": {"messages"},
}


def validate_visualization_spec(
    value: VisualizationSpec | Mapping[str, Any],
) -> list[str]:
    spec, errors = _coerce_visualization_spec(value)
    if spec is None:
        return errors
    if errors:
        return errors
    return _validate_visualization_spec_dataclass(spec)


def visualization_to_dict(
    value: VisualizationSpec | Mapping[str, Any],
) -> dict[str, Any]:
    spec, errors = _coerce_visualization_spec(value)
    if spec is None:
        raise ValueError("; ".join(errors) or "cannot coerce visualization spec")
    normalized = _to_jsonable(asdict(spec))
    if not isinstance(normalized, dict):
        raise ValueError("visualization spec did not normalize to a mapping")
    return normalized


def _validate_visualization_spec_dataclass(spec: VisualizationSpec) -> list[str]:
    errors: list[str] = []
    if spec.schema_version != VISUALIZATION_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {VISUALIZATION_SCHEMA_VERSION}"
        )
    errors.extend(_validate_world(spec.world))
    layer_ids: set[str] = set()
    for primitive in spec.static_primitives:
        errors.extend(_validate_static_primitive(primitive, spec.world))
        if primitive.id in layer_ids:
            errors.append(f"duplicate visualization id: {primitive.id}")
        layer_ids.add(primitive.id)
    for layer in spec.dynamic_layers:
        errors.extend(_validate_dynamic_layer(layer))
        if layer.id in layer_ids:
            errors.append(f"duplicate visualization id: {layer.id}")
        layer_ids.add(layer.id)
    if not spec.views:
        errors.append("visualization spec must declare at least one view")
    view_ids: set[str] = set()
    for view in spec.views:
        errors.extend(_validate_view(view, spec.world, layer_ids))
        if view.id in view_ids:
            errors.append(f"duplicate view id: {view.id}")
        view_ids.add(view.id)
    return errors


def validate_scenario_descriptor(descriptor: ScenarioDescriptor) -> list[str]:
    if descriptor.visualization is None:
        return []
    return validate_visualization_spec(descriptor.visualization)


def validate_frame_packet(
    frame: FramePacket,
    descriptor: ScenarioDescriptor,
) -> list[str]:
    errors: list[str] = []
    if descriptor.visualization is None:
        return errors
    dimension = descriptor.visualization.world.dimension
    for entity in frame.entities:
        entity_id = str(entity.get("id", "<unknown>"))
        errors.extend(
            _validate_vector(
                f"entity {entity_id} position",
                entity.get("position"),
                dimension,
            )
        )
        if "velocity" in entity:
            errors.extend(
                _validate_vector(
                    f"entity {entity_id} velocity",
                    entity.get("velocity"),
                    dimension,
                )
            )
        if "goal" in entity:
            errors.extend(
                _validate_vector(
                    f"entity {entity_id} goal",
                    entity.get("goal"),
                    dimension,
                )
            )
    for index, field in enumerate(frame.fields):
        if "vector" in field:
            errors.extend(
                _validate_vector(
                    f"field {index} vector",
                    field.get("vector"),
                    dimension,
                )
            )
    return errors


def _validate_world(world: WorldSpec) -> list[str]:
    errors: list[str] = []
    if world.dimension not in {2, 3}:
        errors.append("world.dimension must be 2 or 3")
    errors.extend(_validate_bounds(world.bounds, world.dimension))
    if world.axis_labels and len(world.axis_labels) != world.dimension:
        errors.append("world.axis_labels must match world.dimension")
    return errors


def _validate_bounds(bounds: AxisAlignedBounds, dimension: int) -> list[str]:
    errors: list[str] = []
    if len(bounds.minimum) != dimension or len(bounds.maximum) != dimension:
        errors.append("world.bounds must match world.dimension")
        return errors
    for axis, (lower, upper) in enumerate(zip(bounds.minimum, bounds.maximum)):
        if not _is_finite_number(lower) or not _is_finite_number(upper):
            errors.append(f"world.bounds axis {axis} must be finite")
            continue
        if lower >= upper:
            errors.append(f"world.bounds axis {axis} minimum must be < maximum")
    return errors


def _validate_static_primitive(
    primitive: StaticPrimitive,
    world: WorldSpec,
) -> list[str]:
    errors: list[str] = []
    if not primitive.id:
        errors.append("static primitive id must be non-empty")
    if primitive.kind not in STATIC_PRIMITIVE_KINDS:
        errors.append(
            f"static primitive {primitive.id or '<unknown>'} kind must be one of {STATIC_PRIMITIVE_KINDS}"
        )
    if primitive.center is not None:
        errors.extend(
            _validate_vector(
                f"static primitive {primitive.id} center",
                primitive.center,
                world.dimension,
            )
        )
    for index, point in enumerate(primitive.points):
        errors.extend(
            _validate_vector(
                f"static primitive {primitive.id} point {index}",
                point,
                world.dimension,
            )
        )
    if primitive.kind == "ring":
        if primitive.center is None:
            errors.append(f"ring {primitive.id} must define center")
        if not _is_finite_number(primitive.radius) or float(primitive.radius) <= 0.0:
            errors.append(f"ring {primitive.id} must define a positive radius")
    if primitive.kind == "boundary_box":
        if primitive.center is None:
            errors.append(f"boundary_box {primitive.id} must define center")
        minimum = primitive.metadata.get("minimum")
        maximum = primitive.metadata.get("maximum")
        if minimum is not None:
            errors.extend(
                _validate_vector(
                    f"boundary_box {primitive.id} minimum",
                    minimum,
                    world.dimension,
                )
            )
        if maximum is not None:
            errors.extend(
                _validate_vector(
                    f"boundary_box {primitive.id} maximum",
                    maximum,
                    world.dimension,
                )
            )
    return errors


def _validate_dynamic_layer(layer: DynamicLayerSpec) -> list[str]:
    errors: list[str] = []
    if not layer.id:
        errors.append("dynamic layer id must be non-empty")
    if layer.kind not in DYNAMIC_LAYER_KINDS:
        errors.append(
            f"dynamic layer {layer.id or '<unknown>'} kind must be one of {DYNAMIC_LAYER_KINDS}"
        )
    if layer.source not in LAYER_SOURCE_ALLOWLIST:
        errors.append(
            f"dynamic layer {layer.id or '<unknown>'} source must be one of {LAYER_SOURCE_ALLOWLIST}"
        )
    allowed_sources = _LAYER_KIND_TO_SOURCES.get(layer.kind)
    if allowed_sources is not None and layer.source not in allowed_sources:
        errors.append(
            f"dynamic layer {layer.id or '<unknown>'} source {layer.source} is incompatible with kind {layer.kind}"
        )
    return errors


def _validate_view(
    view: ViewSpec,
    world: WorldSpec,
    available_layer_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not view.id:
        errors.append("view id must be non-empty")
    if view.projection not in VIEW_PROJECTIONS:
        errors.append(f"view {view.id or '<unknown>'} projection must be one of {VIEW_PROJECTIONS}")
    if view.projection == "3d" and world.dimension != 3:
        errors.append(f"view {view.id or '<unknown>'} cannot use 3d projection in a 2d world")
    if not view.layer_ids:
        errors.append(f"view {view.id or '<unknown>'} must reference at least one layer")
    for layer_id in view.layer_ids:
        if layer_id not in available_layer_ids:
            errors.append(f"view {view.id or '<unknown>'} references unknown layer id {layer_id}")
    return errors


def _validate_vector(name: str, value: Any, dimension: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return [f"{name} must be a {dimension}D sequence"]
    if len(value) != dimension:
        return [f"{name} must have length {dimension}"]
    errors: list[str] = []
    for component in value:
        if not _is_finite_number(component):
            errors.append(f"{name} must contain only finite numbers")
            break
    return errors


def _is_finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _coerce_visualization_spec(
    value: VisualizationSpec | Mapping[str, Any],
) -> tuple[VisualizationSpec | None, list[str]]:
    if isinstance(value, VisualizationSpec):
        return value, []
    if not isinstance(value, Mapping):
        return None, ["visualization spec must be a VisualizationSpec or mapping"]
    try:
        return (
            VisualizationSpec(
                world=_coerce_world(value.get("world")),
                static_primitives=tuple(
                    _coerce_static_primitive(item)
                    for item in _coerce_sequence(value.get("static_primitives", ()))
                ),
                dynamic_layers=tuple(
                    _coerce_dynamic_layer(item)
                    for item in _coerce_sequence(value.get("dynamic_layers", ()))
                ),
                views=tuple(
                    _coerce_view(item)
                    for item in _coerce_sequence(value.get("views", ()))
                ),
                disclosures=tuple(str(item) for item in _coerce_sequence(value.get("disclosures", ()))),
                schema_version=str(value.get("schema_version", "scenario_visualization/v1")),
            ),
            [],
        )
    except (TypeError, ValueError) as error:
        return None, [f"cannot coerce visualization spec: {error}"]


def _coerce_world(value: Any) -> WorldSpec:
    if isinstance(value, WorldSpec):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("world must be a mapping")
    bounds = value.get("bounds")
    if isinstance(bounds, AxisAlignedBounds):
        coerced_bounds = bounds
    elif isinstance(bounds, Mapping):
        coerced_bounds = AxisAlignedBounds(
            minimum=tuple(float(item) for item in _coerce_sequence(bounds.get("minimum"))),
            maximum=tuple(float(item) for item in _coerce_sequence(bounds.get("maximum"))),
        )
    else:
        raise TypeError("world.bounds must be a mapping")
    axis_labels = tuple(str(item) for item in _coerce_sequence(value.get("axis_labels", ())))
    return WorldSpec(
        dimension=int(value.get("dimension")),
        bounds=coerced_bounds,
        units=str(value.get("units", "abstract")),
        axis_labels=axis_labels,
    )


def _coerce_static_primitive(value: Any) -> StaticPrimitive:
    if isinstance(value, StaticPrimitive):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("static primitive must be a mapping")
    points = tuple(
        tuple(float(component) for component in _coerce_sequence(point))
        for point in _coerce_sequence(value.get("points", ()))
    )
    center_value = value.get("center")
    center = None
    if center_value is not None:
        center = tuple(float(component) for component in _coerce_sequence(center_value))
    radius_value = value.get("radius")
    radius = None if radius_value is None else float(radius_value)
    return StaticPrimitive(
        id=str(value.get("id", "")),
        kind=str(value.get("kind", "")),
        label=str(value.get("label", "")),
        points=points,
        center=center,
        radius=radius,
        style=dict(value.get("style", {})),
        metadata=dict(value.get("metadata", {})),
    )


def _coerce_dynamic_layer(value: Any) -> DynamicLayerSpec:
    if isinstance(value, DynamicLayerSpec):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("dynamic layer must be a mapping")
    return DynamicLayerSpec(
        id=str(value.get("id", "")),
        kind=str(value.get("kind", "")),
        source=str(value.get("source", "")),
        label=str(value.get("label", "")),
        attribute=None
        if value.get("attribute") is None
        else str(value.get("attribute")),
        style=dict(value.get("style", {})),
        enabled_by_default=bool(value.get("enabled_by_default", True)),
    )


def _coerce_view(value: Any) -> ViewSpec:
    if isinstance(value, ViewSpec):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("view must be a mapping")
    return ViewSpec(
        id=str(value.get("id", "")),
        projection=str(value.get("projection", "")),
        label=str(value.get("label", "")),
        layer_ids=tuple(str(item) for item in _coerce_sequence(value.get("layer_ids", ()))),
        camera=dict(value.get("camera", {})),
    )


def _coerce_sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise TypeError("expected a sequence")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value
