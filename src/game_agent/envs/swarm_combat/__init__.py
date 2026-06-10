"""Swarm Combat Environment -- 3D 多无人机红蓝对抗仿真.

从 example-inner (mvp_inner_loop) 载入的模块化环境实现，包含：
- SwarmCombatEnv: 主环境，全局可观测
- EnvConfig: 嵌套 dataclass 配置
- 子模块: entities, dynamics, constraints, rewards, terminations, evaluation, visualizer, rl_wrapper
"""

from game_agent.envs.swarm_combat.env import SwarmCombatEnv
from game_agent.envs.swarm_combat.config import EnvConfig
from game_agent.envs.swarm_combat.entities import Drone, Gate, Team, Role
from game_agent.envs.swarm_combat.dynamics import (
    DynamicsModel,
    DoubleIntegrator3D,
    DampedDoubleIntegrator3D,
    build_dynamics,
)
from game_agent.envs.swarm_combat.constraints import Constraint, build_default_constraints
from game_agent.envs.swarm_combat.rewards import RewardComponent, build_default_rewards
from game_agent.envs.swarm_combat.terminations import TerminationCondition, build_default_terminations
from game_agent.envs.swarm_combat.rl_wrapper import SwarmCombatParallelEnv

__all__ = [
    "SwarmCombatEnv",
    "SwarmCombatParallelEnv",
    "EnvConfig",
    "Drone",
    "Gate",
    "Team",
    "Role",
    "DynamicsModel",
    "DoubleIntegrator3D",
    "DampedDoubleIntegrator3D",
    "build_dynamics",
    "Constraint",
    "build_default_constraints",
    "RewardComponent",
    "build_default_rewards",
    "TerminationCondition",
    "build_default_terminations",
]
