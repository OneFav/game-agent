"""参考策略实现（从 example-inner / mvp_inner_loop 载入）。

包含：
- SafeRulePolicy：原生接口，完整环境状态访问，批量计算动作
- SafeRulePolicyAdapter：适配 contracts.policy_protocol.Policy ABC 的包装器
"""

from __future__ import annotations

from typing import Any

import numpy as np

from contracts.policy_protocol import Policy
from game_agent.envs.swarm_combat.entities import Team, Role
from game_agent.policy_designer.reference_policies.safe_rule_policy import SafeRulePolicy


class SafeRulePolicyAdapter(Policy):
    """将 SafeRulePolicy 包装为 contracts.policy_protocol.Policy ABC。

    SafeRulePolicy 的原生接口（compute_actions(env) 批量模式、完整环境状态访问）
    与 Policy ABC（act(obs, agent_id) 单智能体模式、仅观测向量）根本不同。
    此适配器在单智能体调用时内部做批量计算并缓存，提高效率。
    """

    def __init__(self, config: dict | None = None, env_spec: dict | None = None):
        config = config or {}
        env_spec = env_spec or {}
        self._policy = SafeRulePolicy(
            desired_speed=config.get("desired_speed", 4.0),
            position_gain=config.get("position_gain", 1.2),
            velocity_gain=config.get("velocity_gain", 2.2),
            risk_margin=config.get("risk_margin", 0.6),
            boundary_margin=config.get("boundary_margin", 1.2),
            turn_steps=config.get("turn_steps", 12),
            turn_lookahead=config.get("turn_lookahead", 5.0),
            risk_lookahead_steps=config.get("risk_lookahead_steps", 18),
            brake_release_speed=config.get("brake_release_speed", 0.35),
            defender_mode=config.get("defender_mode", "escort"),
        )
        self._action_low = np.array(env_spec.get("action_space", {}).get("low", [-1.0, -1.0, -1.0]))
        self._action_high = np.array(env_spec.get("action_space", {}).get("high", [1.0, 1.0, 1.0]))
        self._last_actions: dict[int, np.ndarray] = {}
        self._batch_computed = False
        self._step_counter = 0

    def reset(self, seed: int) -> None:
        self._last_actions = {}
        self._batch_computed = False
        self._step_counter = 0

    def act(self, obs: dict, agent_id: str, info: Any = None) -> np.ndarray:
        """单智能体动作查询。首次调用时批量计算所有智能体动作并缓存。"""
        if not self._batch_computed:
            raise RuntimeError(
                "SafeRulePolicyAdapter requires full env state for batch compute. "
                "Call compute_all(env) first, or use the native SafeRulePolicy interface."
            )
        drone_id = int(agent_id.split("_")[-1]) if "_" in str(agent_id) else int(agent_id)
        action = self._last_actions.get(drone_id, np.zeros(3, dtype=np.float32))
        return np.clip(action, self._action_low, self._action_high)

    def compute_all(self, env) -> dict[int, np.ndarray]:
        """批量计算所有智能体动作（对应 SafeRulePolicy.compute_actions）。"""
        self._policy.reset(env)
        actions = self._policy.compute_actions(env)
        self._last_actions = actions
        self._batch_computed = True
        return actions

    def load(self, checkpoint_path: str) -> None:
        pass  # 规则策略无需加载权重

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "desired_speed": {"type": "number", "default": 4.0, "min": 0.5, "max": 20.0},
            "position_gain": {"type": "number", "default": 1.2, "min": 0.1, "max": 10.0},
            "velocity_gain": {"type": "number", "default": 2.2, "min": 0.1, "max": 10.0},
            "risk_margin": {"type": "number", "default": 0.6, "min": 0.0, "max": 5.0},
            "boundary_margin": {"type": "number", "default": 1.2, "min": 0.0, "max": 5.0},
            "turn_steps": {"type": "integer", "default": 12, "min": 2, "max": 100},
            "turn_lookahead": {"type": "number", "default": 5.0, "min": 0.5, "max": 30.0},
            "risk_lookahead_steps": {"type": "integer", "default": 18, "min": 2, "max": 200},
            "brake_release_speed": {"type": "number", "default": 0.35, "min": 0.0, "max": 5.0},
            "defender_mode": {"type": "string", "enum": ["escort", "intercept"], "default": "escort"},
        }

    def supports_training(self) -> bool:
        return False

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "policy_type": "SafeRulePolicyAdapter",
            "native_policy": "SafeRulePolicy",
        }


__all__ = ["SafeRulePolicy", "SafeRulePolicyAdapter"]
