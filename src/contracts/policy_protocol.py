from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class Policy(ABC):
    """All generated policies must implement this protocol."""

    @abstractmethod
    def reset(self, seed: int) -> None:
        """Reset deterministic internal state."""

    @abstractmethod
    def act(self, obs: dict[str, np.ndarray], agent_id: str, info: dict[str, Any] | None = None) -> np.ndarray:
        """Return one bounded action for one agent."""

    @abstractmethod
    def load(self, checkpoint_path: str) -> None:
        """Load policy parameters."""

    @abstractmethod
    def get_config_schema(self) -> dict[str, Any]:
        """Return fields AutoResearch may vary."""

    def supports_training(self) -> bool:
        return True

    def get_diagnostics(self) -> dict[str, Any]:
        return {}
