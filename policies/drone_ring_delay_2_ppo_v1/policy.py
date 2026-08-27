from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from contracts.policy_protocol import Policy
from game_agent.rl import build_algorithm, scale_action


METHOD_NAME = "independent_ppo_red_vs_frozen_blue"
PREPROCESSING_ID = "drone_ring_obs_scale_v1"
OBS_DIM = 12
SCENARIO_ACTION_DIM = 4
LEARNED_ACTION_DIM = 2
AGENT_COUNT = 2

_OBS_SCALE = np.asarray(
    [10.0, 10.0, 5.0, 5.0, 10.0, 10.0, 5.0, 5.0, 1.0, 1.0, 1.0, 10.0],
    dtype=np.float32,
)


def normalize_observation(observation: np.ndarray) -> np.ndarray:
    array = np.asarray(observation, dtype=np.float32)
    if array.shape != (OBS_DIM,):
        raise ValueError(f"observation shape must be {(OBS_DIM,)}, got {array.shape}")
    return np.clip(array / _OBS_SCALE, -5.0, 5.0).astype(np.float32)


def red_action_from_normalized(
    normalized_action: np.ndarray,
    env_spec: dict[str, Any],
) -> np.ndarray:
    action_space = env_spec.get("action_space", {})
    low = np.asarray(action_space.get("low", [-2.0, -2.0, -1.0, -1.0]), dtype=np.float32)
    high = np.asarray(action_space.get("high", [2.0, 2.0, 1.0, 1.0]), dtype=np.float32)
    if low.shape != (SCENARIO_ACTION_DIM,) or high.shape != (SCENARIO_ACTION_DIM,):
        raise ValueError("scenario action contract must have shape [4]")
    action = np.zeros(SCENARIO_ACTION_DIM, dtype=np.float32)
    action[:LEARNED_ACTION_DIM] = scale_action(
        normalized_action,
        low[:LEARNED_ACTION_DIM],
        high[:LEARNED_ACTION_DIM],
    )
    return np.clip(action, low, high).astype(np.float32)


def frozen_blue_action(
    observation: np.ndarray,
    config: dict[str, Any],
    env_spec: dict[str, Any],
) -> np.ndarray:
    array = np.asarray(observation, dtype=np.float32)
    if array.shape != (OBS_DIM,):
        raise ValueError(f"observation shape must be {(OBS_DIM,)}, got {array.shape}")
    target = array[4:6] + float(config.get("blue_lead", 0.15)) * array[6:8]
    direction = target / max(float(np.linalg.norm(target)), 1e-6)
    normalized = np.clip(
        direction * float(config.get("frozen_blue_gain", 0.08)),
        -1.0,
        1.0,
    )
    return red_action_from_normalized(normalized.astype(np.float32), env_spec)


def build_ppo(config: dict[str, Any], *, device: str = "cpu") -> Any:
    hidden_size = int(config.get("hidden_size", 64))
    return build_algorithm(
        "ppo",
        obs_dim=OBS_DIM,
        action_dim=LEARNED_ACTION_DIM,
        hidden_dims=(hidden_size, hidden_size),
        lr_actor=float(config.get("learning_rate", 3e-4)),
        lr_critic=float(config.get("critic_learning_rate", 1e-3)),
        gamma=float(config.get("gamma", 0.99)),
        gae_lambda=float(config.get("gae_lambda", 0.95)),
        clip_ratio=float(config.get("clip_ratio", 0.2)),
        ppo_epochs=int(config.get("ppo_epochs", 4)),
        batch_size=int(config.get("batch_size", 64)),
        target_kl=float(config.get("target_kl", 0.03)),
        max_action=1.0,
        activation=str(config.get("activation", "tanh")),
        device=device,
    )


class PolicyClass(Policy):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        env_spec: dict[str, Any] | None = None,
    ) -> None:
        self.config = dict(config or {})
        self.env_spec = dict(env_spec or {})
        torch.manual_seed(int(self.config.get("initialization_seed", 23)))
        self._algorithm = build_ppo(self.config, device="cpu")
        self._seed = 0
        self._checkpoint_path: str | None = None

    def reset(self, seed: int) -> None:
        self._seed = int(seed)
        np.random.seed(self._seed)
        torch.manual_seed(self._seed)

    def act(
        self,
        obs: dict[str, np.ndarray],
        agent_id: str,
        info: dict[str, Any] | None = None,
    ) -> np.ndarray:
        del info
        observation = np.asarray(obs[agent_id], dtype=np.float32)
        if agent_id == "red_0":
            normalized, _log_prob, _value = self._algorithm.select_action(
                normalize_observation(observation),
                deterministic=True,
            )
            return red_action_from_normalized(normalized, self.env_spec)
        return frozen_blue_action(observation, self.config, self.env_spec)

    def load(self, checkpoint_path: str) -> None:
        path = Path(checkpoint_path)
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        binding = checkpoint.get("policy_binding")
        expected = {
            "method": METHOD_NAME,
            "observation_dim": OBS_DIM,
            "scenario_action_dim": SCENARIO_ACTION_DIM,
            "learned_action_dim": LEARNED_ACTION_DIM,
            "agent_count": AGENT_COUNT,
            "parameter_sharing": "none",
            "preprocessing": PREPROCESSING_ID,
        }
        if binding != expected:
            raise ValueError(
                f"checkpoint policy binding mismatch: expected {expected!r}, got {binding!r}"
            )
        self._algorithm.load(str(path))
        self._checkpoint_path = str(path)

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "learning_rate": {"type": "number", "minimum": 1e-5, "maximum": 1e-2},
            "progress_reward_weight": {"type": "number", "minimum": 0.0, "maximum": 5.0},
        }

    def supports_training(self) -> bool:
        return True

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "method": METHOD_NAME,
            "seed": self._seed,
            "checkpoint_path": self._checkpoint_path,
            "trained_party": "red_0",
            "frozen_party": "blue_0",
        }
