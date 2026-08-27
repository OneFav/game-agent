from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def _add_source_root() -> None:
    for parent in Path(__file__).resolve().parents:
        source_root = parent / "src"
        if (source_root / "contracts" / "policy_protocol.py").is_file():
            if str(source_root) not in sys.path:
                sys.path.insert(0, str(source_root))
            return


_add_source_root()

from contracts.policy_protocol import Policy


PREPROCESSING_ID = "max_space_local_obs_v1"


class _BoundedGoalController:
    """Pure local-observation controller used by one explicit dispatch branch."""

    def __init__(self, config: Mapping[str, Any], prefix: str) -> None:
        self._target_gain = float(config[f"{prefix}_target_gain"])
        self._velocity_gain = float(config[f"{prefix}_velocity_gain"])
        self._action_scale = float(config[f"{prefix}_action_scale"])
        self._norm_limit = float(config["shared_norm_limit"])
        self._message_stale_gain = float(config["shared_message_stale_gain"])
        self._minimum_scale = float(config["shared_minimum_scale"])
        self._terminal_brake_gain = float(config["shared_terminal_brake_gain"])
        self._controller_kind = str(config["controller_kind"])

    def action(self, local: np.ndarray, dimension: int) -> np.ndarray:
        velocity = local[dimension : 2 * dimension]
        target_delta = local[2 * dimension : 3 * dimension]
        distance = float(np.linalg.norm(target_delta))
        direction = _normalize(target_delta)
        velocity_gain = self._velocity_gain
        if self._controller_kind == "terminal_state_pd" and distance < 0.35:
            velocity_gain = max(velocity_gain, self._terminal_brake_gain)
        message_age = float(local[3 * dimension + 2])
        stale_scale = max(
            self._minimum_scale,
            1.0 - self._message_stale_gain * float(np.clip(message_age, 0.0, 1.0)),
        )
        raw = stale_scale * self._action_scale * (
            self._target_gain * direction - velocity_gain * velocity
        )
        norm = float(np.linalg.norm(raw))
        if norm > self._norm_limit:
            raw = raw * (self._norm_limit / max(norm, 1e-8))
        return np.asarray(raw, dtype=np.float32)


class RedPolicy(_BoundedGoalController):
    """Only red-side behavior; it reads red-prefixed parameters."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        super().__init__(config, "red")


class BluePolicy(_BoundedGoalController):
    """Only blue-side behavior; it reads blue-prefixed parameters."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        super().__init__(config, "blue")


class SharedPolicy(_BoundedGoalController):
    """Cooperative/single-agent behavior using explicitly shared parameters."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        super().__init__(config, "shared")


def create_policy_class(package_spec: Mapping[str, Any]) -> type[Policy]:
    """Create the package-specific Policy ABC adapter without global state."""

    frozen_spec = dict(package_spec)
    default_config = dict(frozen_spec["default_config"])
    config_schema = dict(frozen_spec["config_schema"])

    class MaxSpaceRulePolicy(Policy):
        PACKAGE_SPEC = frozen_spec

        def __init__(
            self,
            config: dict[str, Any] | None = None,
            env_spec: dict[str, Any] | None = None,
        ) -> None:
            self.config = _validate_config(default_config, config_schema, config or {})
            self.env_spec = dict(env_spec or {})
            self._state_dimension = int(frozen_spec["dimension"])
            self._action_low, self._action_high = _resolve_action_bounds(
                self.env_spec, self._state_dimension
            )
            self._action_dim = int(self._action_low.size)
            self._seed = 0
            self._checkpoint_path: str | None = None
            self._red = RedPolicy(self.config)
            self._blue = BluePolicy(self.config)
            self._shared = SharedPolicy(self.config)

        def reset(self, seed: int) -> None:
            self._seed = int(seed)

        def act(
            self,
            obs: dict[str, np.ndarray] | Any,
            agent_id: str,
            info: dict[str, Any] | None = None,
        ) -> np.ndarray:
            try:
                if frozen_spec.get("zero_policy", False):
                    return np.zeros(self._action_dim, dtype=np.float32)
                local = _local_vector(obs, str(agent_id), self._state_dimension)
                team = _execution_team(local, str(agent_id), info, frozen_spec)
                controller = self._red if team == "red" else self._blue if team == "blue" else self._shared
                command = controller.action(local, self._state_dimension)
                shaped = np.zeros(self._action_dim, dtype=np.float32)
                used = min(self._state_dimension, self._action_dim, command.size)
                shaped[:used] = command[:used]
                shield_low = np.minimum(self._action_low, self._action_high)
                shield_high = np.maximum(self._action_low, self._action_high)
                return np.clip(shaped, shield_low, shield_high).astype(np.float32)
            except Exception:
                return np.zeros(self._action_dim, dtype=np.float32)

        def load(self, checkpoint_path: str) -> None:
            path = Path(checkpoint_path)
            if not path.is_file():
                raise FileNotFoundError(f"checkpoint does not exist: {path}")
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"invalid rule-policy checkpoint: {path}") from error
            binding = payload.get("checkpoint_binding", {})
            if not isinstance(binding, dict):
                raise ValueError("checkpoint_binding must be a mapping")
            expected = {
                "policy_id": str(frozen_spec["policy_id"]),
                "method": str(frozen_spec["method_name"]),
                "action_dimension": self._state_dimension,
                "preprocessing": PREPROCESSING_ID,
            }
            for key, value in expected.items():
                if binding.get(key) != value:
                    raise ValueError(
                        f"checkpoint {key} mismatch: expected {value!r}, got {binding.get(key)!r}"
                    )
            checkpoint_config = payload.get("config", {})
            if not isinstance(checkpoint_config, dict):
                raise ValueError("checkpoint config must be a mapping")
            self.config = _validate_config(default_config, config_schema, checkpoint_config)
            self._red = RedPolicy(self.config)
            self._blue = BluePolicy(self.config)
            self._shared = SharedPolicy(self.config)
            self._checkpoint_path = str(path)

        def get_config_schema(self) -> dict[str, Any]:
            return {name: dict(rule) for name, rule in config_schema.items()}

        def supports_training(self) -> bool:
            return False

        def get_diagnostics(self) -> dict[str, Any]:
            return {
                "policy_id": str(frozen_spec["policy_id"]),
                "scenario_id": str(frozen_spec["scenario_id"]),
                "method": str(frozen_spec["method_name"]),
                "seed": self._seed,
                "checkpoint_path": self._checkpoint_path,
                "preprocessing": PREPROCESSING_ID,
            }

    MaxSpaceRulePolicy.__name__ = f"{str(frozen_spec['scenario_id']).title()}Policy"
    MaxSpaceRulePolicy.__qualname__ = MaxSpaceRulePolicy.__name__
    return MaxSpaceRulePolicy


def _validate_config(
    defaults: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    unknown = sorted(set(overrides) - set(schema))
    if unknown:
        raise ValueError(f"unknown config fields: {', '.join(unknown)}")
    values = dict(defaults)
    values.update(overrides)
    for name, rule in schema.items():
        if name not in values:
            raise ValueError(f"missing config field: {name}")
        value = values[name]
        kind = rule.get("type")
        if kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            numeric = float(value)
            if numeric < float(rule["minimum"]) or numeric > float(rule["maximum"]):
                raise ValueError(f"{name} outside schema range")
            values[name] = numeric
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < int(rule["minimum"]) or value > int(rule["maximum"]):
                raise ValueError(f"{name} outside schema range")
        elif kind == "string":
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            allowed = rule.get("enum")
            if allowed is not None and value not in allowed:
                raise ValueError(f"{name} outside schema enum")
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a boolean")
        else:
            raise ValueError(f"unsupported schema type for {name}: {kind}")
    return values


def _resolve_action_bounds(
    env_spec: Mapping[str, Any], expected_dimension: int
) -> tuple[np.ndarray, np.ndarray]:
    action_space: Any = env_spec.get("action_space")
    if not isinstance(action_space, Mapping):
        action_spaces = env_spec.get("action_spaces")
        if isinstance(action_spaces, Mapping) and action_spaces:
            action_space = next(iter(action_spaces.values()))
    if isinstance(action_space, Mapping) and action_space.get("type") == "Dict":
        fields = action_space.get("fields", {})
        if isinstance(fields, Mapping):
            action_space = fields.get("control", {})
    if not isinstance(action_space, Mapping):
        action_space = {}
    shape = action_space.get("shape", [expected_dimension])
    action_dim = int(shape[0]) if isinstance(shape, (list, tuple)) and shape else expected_dimension
    low = _bound_vector(action_space.get("low", -1.0), action_dim, -1.0)
    high = _bound_vector(action_space.get("high", 1.0), action_dim, 1.0)
    if not np.all(np.isfinite(low)) or not np.all(np.isfinite(high)):
        raise ValueError("action bounds must be finite")
    return low, high


def _bound_vector(value: Any, dimension: int, fallback: float) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if array.size == 0:
        return np.full(dimension, fallback, dtype=np.float32)
    if array.size == 1:
        return np.full(dimension, float(array[0]), dtype=np.float32)
    if array.size != dimension:
        raise ValueError("action bound dimension mismatch")
    return array.astype(np.float32, copy=True)


def _local_vector(obs: Any, agent_id: str, dimension: int) -> np.ndarray:
    value = obs
    if isinstance(obs, Mapping) and agent_id in obs:
        value = obs[agent_id]
    if isinstance(value, Mapping):
        if "proprioception" in value:
            value = value["proprioception"]
        elif "self_state" in value:
            value = value["self_state"]
        elif "graph" in value and isinstance(value["graph"], Mapping):
            value = _graph_self_proxy(value["graph"], dimension)
        elif "nodes" in value:
            value = _graph_self_proxy(value, dimension)
        else:
            raise ValueError("structured observation lacks execution proprioception")
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    required = 3 * dimension + 4
    if vector.size < required or not np.all(np.isfinite(vector[:required])):
        raise ValueError("invalid local observation vector")
    return vector[:required].copy()


def _graph_self_proxy(graph: Mapping[str, Any], dimension: int) -> np.ndarray:
    nodes = np.asarray(graph.get("nodes", []), dtype=np.float32)
    required = 3 * dimension + 4
    proxy = np.zeros(required, dtype=np.float32)
    if nodes.ndim != 2 or nodes.shape[0] == 0 or nodes.shape[1] < 2 * dimension + 2:
        return proxy
    self_index = int(np.argmax(nodes[:, -1]))
    proxy[dimension : 2 * dimension] = nodes[self_index, dimension : 2 * dimension]
    proxy[-1] = nodes[self_index, -2]
    return proxy


def _execution_team(
    local: np.ndarray,
    agent_id: str,
    info: Mapping[str, Any] | None,
    package_spec: Mapping[str, Any],
) -> str:
    local_info: Mapping[str, Any] = info or {}
    if agent_id in local_info and isinstance(local_info[agent_id], Mapping):
        local_info = local_info[agent_id]
    team = str(local_info.get("team", "")).lower()
    if team in {"red", "blue"}:
        return team
    role = str(local_info.get("role", "")).lower()
    if role in {"pursuer", "escort", "asset"}:
        return "red"
    if role in {"evader", "interceptor"}:
        return "blue"
    role_code = float(local[3 * int(package_spec["dimension"]) + 3])
    if abs(role_code - 0.2) < 0.05 or abs(role_code - 0.5) < 0.05 or abs(role_code - 0.6) < 0.05:
        return "red"
    if abs(role_code - 0.4) < 0.05 or abs(role_code - 0.7) < 0.05:
        return "blue"
    lowered = agent_id.lower()
    if lowered.startswith("red") or "pursuer" in lowered or "escort" in lowered:
        return "red"
    if lowered.startswith("blue") or "evader" in lowered or "interceptor" in lowered:
        return "blue"
    return "shared"


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        return np.zeros_like(vector, dtype=np.float32)
    return np.asarray(vector / norm, dtype=np.float32)
