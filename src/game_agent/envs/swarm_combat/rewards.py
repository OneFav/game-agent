"""
奖励模块
组件化设计，每个组件独立、带权重，最终加权求和
按 role 启用不同子集
"""
from abc import ABC, abstractmethod
from typing import List, Dict
import numpy as np
from game_agent.envs.swarm_combat.entities import Drone, Gate, Team, Role


class RewardComponent(ABC):
    """奖励组件基类"""
    name: str = "base"

    @abstractmethod
    def compute(self, ctx: Dict) -> Dict[int, float]:
        """
        ctx 包含本步所有信息：
            drones, gates, dt, step, pass_events, collision_info, ...
        返回 {drone_id: reward_value}
        """
        ...


class GatePassReward(RewardComponent):
    """穿门基础分（仅 RACER 享受）"""
    name = "gate_pass"

    def __init__(self, weight: float):
        self.w = weight

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        for ev in ctx["pass_events"]:
            # ev = {"drone_id":..., "gate_id":..., "scored": bool}
            if ev["scored"]:
                rewards[ev["drone_id"]] += self.w
        return rewards


class FormationTightnessReward(RewardComponent):
    """
    编队紧密度奖励：穿门时刻，同队 RACER 之间距离越近奖励越高
    形式：reward = w * exp(-mean_pairwise_dist / scale)
    """
    name = "formation_tightness"

    def __init__(self, weight: float, scale: float = 3.0):
        self.w = weight
        self.scale = scale

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        if not ctx["pass_events"]:
            return rewards
        drones = ctx["drones"]
        for ev in ctx["pass_events"]:
            if not ev["scored"]:
                continue
            scorer = next(d for d in drones if d.id == ev["drone_id"])
            teammates = [d for d in drones
                         if d.team == scorer.team and d.role == Role.RACER and d.id != scorer.id]
            if not teammates:
                continue
            dists = [np.linalg.norm(scorer.position - t.position) for t in teammates]
            mean_d = float(np.mean(dists))
            bonus = self.w * np.exp(-mean_d / self.scale)
            rewards[scorer.id] += bonus
        return rewards


class InterceptionReward(RewardComponent):
    """
    阻拦奖励：DEFENDER 接近敌方 RACER 给予正奖励
    简单形式：奖励 = w * sum_{敌RACER} exp(-dist / scale)
    """
    name = "interception"

    def __init__(self, weight: float, scale: float = 4.0):
        self.w = weight
        self.scale = scale

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        drones = ctx["drones"]
        for d in drones:
            if d.role != Role.DEFENDER:
                continue
            enemy_racers = [e for e in drones if e.team != d.team and e.role == Role.RACER]
            if not enemy_racers:
                continue
            score = sum(np.exp(-np.linalg.norm(d.position - e.position) / self.scale)
                        for e in enemy_racers)
            rewards[d.id] += self.w * score / max(len(enemy_racers), 1)
        return rewards


class ProtectionReward(RewardComponent):
    """保护奖励：DEFENDER 靠近己方 RACER 给予小奖励"""
    name = "protection"

    def __init__(self, weight: float, scale: float = 4.0):
        self.w = weight
        self.scale = scale

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        drones = ctx["drones"]
        for d in drones:
            if d.role != Role.DEFENDER:
                continue
            mates = [m for m in drones if m.team == d.team and m.role == Role.RACER]
            if not mates:
                continue
            score = sum(np.exp(-np.linalg.norm(d.position - m.position) / self.scale)
                        for m in mates)
            rewards[d.id] += self.w * score / max(len(mates), 1)
        return rewards


class SafetyViolationPenalty(RewardComponent):
    """
    接近违反安全距离的软惩罚（在硬约束触发前给梯度信号）
    """
    name = "safety_soft"

    def __init__(self, weight: float, d_safe: float, margin: float = 0.5):
        self.w = weight
        self.d_safe = d_safe
        self.margin = margin

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        drones = ctx["drones"]
        threshold = self.d_safe + self.margin
        for i, di in enumerate(drones):
            for j, dj in enumerate(drones):
                if j <= i:
                    continue
                if di.team == dj.team:
                    continue
                dist = np.linalg.norm(di.position - dj.position)
                if dist < threshold:
                    pen = self.w * (threshold - dist) / self.margin
                    rewards[di.id] += pen
                    rewards[dj.id] += pen
        return rewards


class CollisionPenalty(RewardComponent):
    """碰撞大额惩罚（一次性）"""
    name = "collision"

    def __init__(self, weight: float):
        self.w = weight

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        if ctx.get("collision_triggered", False):
            for d in ctx["drones"]:
                rewards[d.id] += self.w
        return rewards


class OutOfBoundsPenalty(RewardComponent):
    name = "out_of_bounds"

    def __init__(self, weight: float):
        self.w = weight

    def compute(self, ctx):
        rewards = {d.id: 0.0 for d in ctx["drones"]}
        for did in ctx.get("oob_ids", []):
            rewards[did] += self.w
        return rewards


class TimePenalty(RewardComponent):
    name = "time"

    def __init__(self, weight: float):
        self.w = weight

    def compute(self, ctx):
        return {d.id: self.w for d in ctx["drones"]}


def build_default_rewards(cfg) -> List[RewardComponent]:
    w = cfg.rewards
    return [
        GatePassReward(w.gate_pass),
        FormationTightnessReward(w.formation_tight),
        InterceptionReward(w.interception),
        ProtectionReward(w.protection),
        SafetyViolationPenalty(w.safety_violation, cfg.drone.inter_team_safe_dist),
        CollisionPenalty(w.collision),
        OutOfBoundsPenalty(w.out_of_bounds),
        TimePenalty(w.time_penalty),
    ]
