from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch


def default_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


class BaseRLAlgorithm(ABC):
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int] = (256, 256),
        lr_actor: float = 3e-4,
        lr_critic: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        device: str | None = None,
    ) -> None:
        if obs_dim <= 0 or action_dim <= 0:
            raise ValueError("obs_dim and action_dim must be positive")
        if not hidden_dims or any(dimension <= 0 for dimension in hidden_dims):
            raise ValueError("hidden_dims must contain positive dimensions")
        self.obs_dim = int(obs_dim)
        self.action_dim = int(action_dim)
        self.hidden_dims = tuple(int(dimension) for dimension in hidden_dims)
        self.lr_actor = float(lr_actor)
        self.lr_critic = float(lr_critic)
        self.gamma = float(gamma)
        self.tau = float(tau)
        self.device = torch.device(device or default_device())
        self.train_step = 0

    @abstractmethod
    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> Any:
        raise NotImplementedError

    @abstractmethod
    def update(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def save(self, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self, path: str) -> None:
        raise NotImplementedError

    def _soft_update(self, target: torch.nn.Module, source: torch.nn.Module) -> None:
        with torch.no_grad():
            for target_parameter, source_parameter in zip(
                target.parameters(),
                source.parameters(),
                strict=True,
            ):
                target_parameter.mul_(1.0 - self.tau)
                target_parameter.add_(source_parameter, alpha=self.tau)

    def _checkpoint_metadata(self, algorithm: str) -> dict[str, Any]:
        return {
            "algorithm": algorithm,
            "obs_dim": self.obs_dim,
            "action_dim": self.action_dim,
            "hidden_dims": list(self.hidden_dims),
        }

    def _validate_checkpoint_metadata(
        self,
        checkpoint: dict[str, Any],
        *,
        algorithm: str,
    ) -> None:
        metadata = checkpoint.get("metadata")
        if not isinstance(metadata, dict):
            return
        expected = self._checkpoint_metadata(algorithm)
        for key in ("algorithm", "obs_dim", "action_dim", "hidden_dims"):
            if metadata.get(key) != expected[key]:
                raise ValueError(
                    f"checkpoint {key} mismatch: expected {expected[key]!r}, "
                    f"got {metadata.get(key)!r}"
                )
