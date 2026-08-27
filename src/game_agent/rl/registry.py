from __future__ import annotations

from importlib import import_module
from typing import Any


SUPPORTED_ALGORITHMS = ("ddpg", "maddpg", "ppo", "sac")

_ALGORITHM_IMPORTS = {
    "ddpg": ("game_agent.rl.algorithms.ddpg", "DDPG"),
    "maddpg": ("game_agent.rl.algorithms.maddpg", "MADDPG"),
    "ppo": ("game_agent.rl.algorithms.ppo", "PPO"),
    "sac": ("game_agent.rl.algorithms.sac", "SAC"),
}


def get_algorithm_class(name: str) -> type:
    """按名称懒加载算法，避免非 RL 工作流导入 PyTorch。"""

    normalized = name.strip().lower()
    if normalized not in _ALGORITHM_IMPORTS:
        available = ", ".join(SUPPORTED_ALGORITHMS)
        raise ValueError(f"unsupported RL algorithm {name!r}; available: {available}")
    module_name, class_name = _ALGORITHM_IMPORTS[normalized]
    module = import_module(module_name)
    return getattr(module, class_name)


def build_algorithm(name: str, **kwargs: Any) -> Any:
    return get_algorithm_class(name)(**kwargs)
