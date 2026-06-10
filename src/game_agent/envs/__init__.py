"""环境实现——供生成的场景包引用。

两种环境：
- drone_ring_game: M1 轻量 2D 基线（155 行，单块实现）
- swarm_combat:  3D 多无人机红蓝对抗（12 模块，从 mvp_inner_loop 载入）
"""

from game_agent.envs.drone_ring_game.env import DroneRingEnv
from game_agent.envs.swarm_combat.env import SwarmCombatEnv
from game_agent.envs.swarm_combat.config import EnvConfig

__all__ = [
    "DroneRingEnv",
    "SwarmCombatEnv",
    "EnvConfig",
]
