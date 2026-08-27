"""可选的强化学习算法核心。

算法实现仅在通过注册表请求时导入，因此规则策略工作流不要求安装 PyTorch。
"""

from game_agent.rl.action_scaling import scale_action, unscale_action
from game_agent.rl.registry import (
    SUPPORTED_ALGORITHMS,
    build_algorithm,
    get_algorithm_class,
)

__all__ = [
    "SUPPORTED_ALGORITHMS",
    "build_algorithm",
    "get_algorithm_class",
    "scale_action",
    "unscale_action",
]
