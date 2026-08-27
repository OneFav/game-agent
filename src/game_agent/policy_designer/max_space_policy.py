from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from contracts.policy_protocol import Policy


class RedPolicy:
    """Red-side role scaling for pursuit and escort methods."""

    @staticmethod
    def scale(role_code: float, role_gain: float) -> float:
        return 1.0 + role_gain * max(0.4 - role_code, 0.0)


class BluePolicy:
    """Blue-side role scaling for evasion and interception methods."""

    @staticmethod
    def scale(role_code: float, role_gain: float) -> float:
        return 1.0 + role_gain * max(role_code - 0.4, 0.0)


class MaxSpaceRulePolicy(Policy):
    """Observation-only controller shared by the explicit max-space policy packages."""

    PACKAGE_SPEC: dict[str, Any] = {}

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        env_spec: dict[str, Any] | None = None,
    ) -> None:
        package_defaults = dict(self.PACKAGE_SPEC.get("default_config", {}))
        package_defaults.update(config or {})
        self.config = package_defaults
        self.env_spec = dict(env_spec or {})
        self._validate_config(self.config)
        self.strategy = str(self.config.get("strategy", "goal_vector"))
        action_spec = dict(self.env_spec.get("action_space", {}))
        if action_spec.get("type") == "Dict":
            action_spec = dict(action_spec.get("fields", {}).get("control", {}))
        fallback_dimension = int(self.PACKAGE_SPEC.get("dimension", 2))
        shape = tuple(
            int(value) for value in action_spec.get("shape", [fallback_dimension])
        )
        if len(shape) != 1 or shape[0] < 1:
            raise ValueError("max-space policies require a one-dimensional action shape")
        self.action_shape = shape
        self.dimension = shape[0]
        self.action_low = _bound_array(action_spec.get("low", -1.0), shape, -1.0)
        self.action_high = _bound_array(action_spec.get("high", 1.0), shape, 1.0)
        self.gain = float(self.config.get("gain", 1.0))
        self.damping = float(self.config.get("damping", 0.55))
        self.action_cap = float(self.config.get("action_cap", 1.0))
        self.rate_limit = float(self.config.get("rate_limit", 2.0))
        self.communication_decay = float(
            self.config.get("communication_decay", 0.12)
        )
        self.role_gain = float(self.config.get("role_gain", 0.15))
        self.red_policy = RedPolicy()
        self.blue_policy = BluePolicy()
        self._seed = 0

    def reset(self, seed: int) -> None:
        self._seed = int(seed)

    def act(
        self,
        obs: dict[str, Any],
        agent_id: str,
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        try:
            vector = _execution_vector(obs[agent_id])
            required = 3 * self.dimension + 4
            if vector.size < required or not np.all(np.isfinite(vector)):
                return self._zero()
            velocity = vector[self.dimension : 2 * self.dimension]
            target_delta = vector[2 * self.dimension : 3 * self.dimension]
            message_age = max(float(vector[3 * self.dimension + 2]), 0.0)
            role_code = float(vector[3 * self.dimension + 3])
            action = self._strategy_action(
                target_delta, velocity, message_age, role_code
            )
            action = np.clip(action, -self.rate_limit, self.rate_limit)
            safe_low = np.nextafter(self.action_low, self.action_high)
            safe_high = np.nextafter(self.action_high, self.action_low)
            action = np.clip(action, safe_low, safe_high)
            if not np.all(np.isfinite(action)):
                return self._zero()
            return action.astype(np.float32)
        except Exception:
            return self._zero()

    def load(self, checkpoint_path: str) -> None:
        path = Path(checkpoint_path)
        if not path.is_file():
            raise FileNotFoundError(f"checkpoint does not exist: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = self.config.get("policy_id")
        actual = payload.get("policy_id")
        if expected and actual != expected:
            raise ValueError(
                f"checkpoint policy_id mismatch: expected {expected}, got {actual}"
            )
        shape = tuple(int(value) for value in payload.get("action_shape", []))
        if shape != self.action_shape:
            raise ValueError(
                f"checkpoint action shape mismatch: expected {self.action_shape}, got {shape}"
            )
        expected_binding = {
            "method": self.PACKAGE_SPEC.get("method_name"),
            **dict(self.PACKAGE_SPEC.get("checkpoint_binding", {})),
        }
        actual_binding = payload.get("checkpoint_binding", {})
        for field in (
            "method",
            "observation_contract",
            "action_contract",
            "preprocessing",
        ):
            expected_value = expected_binding.get(field)
            if expected_value and actual_binding.get(field) != expected_value:
                raise ValueError(
                    f"checkpoint {field} mismatch: expected {expected_value}, "
                    f"got {actual_binding.get(field)}"
                )

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "strategy": {
                "type": "string",
                "default": self.strategy,
                "enum": [
                    "zero",
                    "goal_vector",
                    "dynamics_pd",
                    "pursuit_role",
                    "team_coordination",
                    "escort_defense",
                    "observation_limited",
                    "communication_aware",
                    "robust_capped",
                    "lifecycle_role",
                    "scalable_adapter",
                ],
            },
            "policy_id": {
                "type": "string",
                "default": str(
                    self.config.get(
                        "policy_id", self.PACKAGE_SPEC.get("policy_id", "unbound")
                    )
                ),
            },
            "gain": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 2.0,
                "default": self.gain,
            },
            "damping": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 2.0,
                "default": self.damping,
            },
            "action_cap": {
                "type": "number",
                "minimum": 0.05,
                "maximum": 1.0,
                "default": self.action_cap,
            },
            "rate_limit": {
                "type": "number",
                "minimum": 0.05,
                "maximum": 2.0,
                "default": self.rate_limit,
            },
            "communication_decay": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": self.communication_decay,
            },
            "role_gain": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": self.role_gain,
            },
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "seed": self._seed,
        }

    def _strategy_action(
        self,
        target_delta: np.ndarray,
        velocity: np.ndarray,
        message_age: float,
        role_code: float,
    ) -> np.ndarray:
        if self.strategy == "zero":
            return self._zero()
        direction = target_delta / max(float(np.linalg.norm(target_delta)), 1e-6)
        if self.strategy == "goal_vector":
            action = self.gain * direction
        elif self.strategy == "dynamics_pd":
            action = self.gain * direction - self.damping * velocity
        elif self.strategy == "pursuit_role":
            component = self.red_policy if role_code < 0.4 else self.blue_policy
            gain = self.gain * component.scale(role_code, self.role_gain)
            action = gain * direction - self.damping * velocity
        elif self.strategy == "team_coordination":
            action = self.gain * direction - self.damping * velocity
        elif self.strategy == "escort_defense":
            component = self.red_policy if role_code <= 0.6 else self.blue_policy
            gain = self.gain * component.scale(role_code, self.role_gain)
            action = gain * direction - self.damping * velocity
        elif self.strategy == "observation_limited":
            action = 0.78 * self.gain * direction - self.damping * velocity
        elif self.strategy == "communication_aware":
            freshness = 1.0 / (1.0 + self.communication_decay * message_age)
            action = freshness * self.gain * direction - self.damping * velocity
        elif self.strategy == "robust_capped":
            action = self.gain * np.tanh(1.4 * direction) - self.damping * velocity
        elif self.strategy == "lifecycle_role":
            relay_scale = 0.65 if role_code >= 0.99 else 1.0
            action = relay_scale * self.gain * direction - self.damping * velocity
        elif self.strategy == "scalable_adapter":
            action = self.gain * direction - self.damping * velocity
        else:
            return self._zero()
        return np.clip(action, -self.action_cap, self.action_cap)

    def _zero(self) -> np.ndarray:
        return np.zeros(self.action_shape, dtype=np.float32)

    def _validate_config(self, config: dict[str, Any]) -> None:
        schema = {
            "strategy": (str, None, None),
            "policy_id": (str, None, None),
            "gain": ((int, float), 0.0, 2.0),
            "damping": ((int, float), 0.0, 2.0),
            "action_cap": ((int, float), 0.05, 1.0),
            "rate_limit": ((int, float), 0.05, 2.0),
            "communication_decay": ((int, float), 0.0, 1.0),
            "role_gain": ((int, float), 0.0, 1.0),
        }
        for name, value in config.items():
            if name not in schema:
                raise ValueError(f"unsupported policy config field: {name}")
            expected_type, minimum, maximum = schema[name]
            if not isinstance(value, expected_type) or isinstance(value, bool):
                raise TypeError(f"invalid type for policy config field: {name}")
            if minimum is not None and not minimum <= float(value) <= maximum:
                raise ValueError(f"policy config field out of range: {name}")
        strategy = str(config.get("strategy", "goal_vector"))
        if strategy not in {
            "zero",
            "goal_vector",
            "dynamics_pd",
            "pursuit_role",
            "team_coordination",
            "escort_defense",
            "observation_limited",
            "communication_aware",
            "robust_capped",
            "lifecycle_role",
            "scalable_adapter",
        }:
            raise ValueError(f"unsupported max-space strategy: {strategy}")


def _execution_vector(observation: Any) -> np.ndarray:
    if isinstance(observation, dict):
        observation = observation.get(
            "proprioception", observation.get("self_state", np.asarray([]))
        )
    return np.asarray(observation, dtype=np.float32).reshape(-1)


def _bound_array(value: Any, shape: tuple[int, ...], fallback: float) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 0:
        array = np.full(shape, float(array), dtype=np.float32)
    if array.shape != shape or not np.all(np.isfinite(array)):
        array = np.full(shape, fallback, dtype=np.float32)
    return array
