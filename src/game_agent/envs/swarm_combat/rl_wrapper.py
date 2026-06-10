"""强化学习框架适配层。

提供接近 PettingZoo ParallelEnv 的接口；如果安装了 gymnasium，会暴露标准
spaces.Box，否则使用轻量 SimpleBox，便于在无额外依赖时先跑通项目测试。
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from game_agent.envs.swarm_combat.config import EnvConfig
from game_agent.envs.swarm_combat.env import SwarmCombatEnv


try:
    from gymnasium import spaces
except ImportError:  # pragma: no cover - 仅在未安装 gymnasium 时启用
    spaces = None


class SimpleBox:
    """最小 Box 兼容对象，用于没有 gymnasium 的环境。"""

    def __init__(self, low, high, shape, dtype=np.float32):
        self.low = low
        self.high = high
        self.shape = shape
        self.dtype = dtype

    def sample(self):
        return np.random.uniform(self.low, self.high, self.shape).astype(self.dtype)

    def contains(self, x):
        arr = np.asarray(x, dtype=self.dtype)
        return arr.shape == self.shape and np.all(arr >= self.low) and np.all(arr <= self.high)


def _box(low, high, shape, dtype=np.float32):
    if spaces is not None:
        return spaces.Box(low=low, high=high, shape=shape, dtype=dtype)
    return SimpleBox(low=low, high=high, shape=shape, dtype=dtype)


class SwarmCombatParallelEnv:
    """PettingZoo parallel 风格 wrapper。"""

    metadata = {"name": "swarm_combat_v0", "is_parallelizable": True}

    def __init__(self, cfg: Optional[EnvConfig] = None):
        self.base_env = SwarmCombatEnv(cfg)
        initial_obs = self.base_env.reset()
        self.possible_agents = [self._agent_name(i) for i in sorted(initial_obs)]
        self.agents = list(self.possible_agents)
        self._obs_dim = len(next(iter(initial_obs.values()))) if initial_obs else 0
        self.observation_spaces = {
            agent: _box(-np.inf, np.inf, (self._obs_dim,), np.float32)
            for agent in self.possible_agents
        }
        accel = self.base_env.cfg.drone.max_accel
        self.action_spaces = {
            agent: _box(-accel, accel, (self.base_env.action_dim,), np.float32)
            for agent in self.possible_agents
        }

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.base_env.rng = np.random.default_rng(seed)
        obs = self.base_env.reset()
        self.agents = [self._agent_name(i) for i in sorted(obs)]
        return self._agent_obs(obs), {agent: {} for agent in self.agents}

    def step(self, actions: Dict[str, np.ndarray]):
        int_actions = {
            self._agent_id(agent): np.asarray(action, dtype=np.float32)
            for agent, action in actions.items()
        }
        obs, rewards, terminated, truncated, info = self.base_env.step(int_actions)
        obs_by_agent = self._agent_obs(obs)
        rewards_by_agent = {self._agent_name(k): float(v) for k, v in rewards.items()}
        terminations = {agent: bool(terminated) for agent in self.agents}
        truncations = {agent: bool(truncated) for agent in self.agents}
        infos = {agent: info for agent in self.agents}
        if terminated or truncated:
            self.agents = []
        return obs_by_agent, rewards_by_agent, terminations, truncations, infos

    def observation_space(self, agent):
        return self.observation_spaces[agent]

    def action_space(self, agent):
        return self.action_spaces[agent]

    def close(self):
        pass

    @staticmethod
    def _agent_name(agent_id: int) -> str:
        return f"drone_{agent_id}"

    @staticmethod
    def _agent_id(agent_name: str) -> int:
        return int(agent_name.split("_")[-1])

    def _agent_obs(self, obs: Dict[int, np.ndarray]):
        return {self._agent_name(k): v for k, v in obs.items()}
