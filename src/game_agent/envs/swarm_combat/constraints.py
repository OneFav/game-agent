"""
约束模块
所有约束统一接口：check / penalty / as_mpc_constraint
环境每步遍历约束列表，便于增删
"""
from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np
from game_agent.envs.swarm_combat.entities import Drone, Gate, Team


class Constraint(ABC):
    """约束基类"""
    name: str = "base"

    @abstractmethod
    def check(self, drones: List[Drone], gates: List[Gate], field_cfg) -> Tuple[bool, dict]:
        """
        返回 (is_violated, info)
        info 字典中包含具体违反细节（哪两架机距离过近、哪架出界等）
        """
        ...


class InterTeamSafetyDistance(Constraint):
    """队间安全距离（硬约束，违反即视为碰撞）"""
    name = "inter_team_safety"

    def __init__(self, d_safe: float):
        self.d_safe = d_safe

    def check(self, drones, gates, field_cfg):
        violators = []
        for i, di in enumerate(drones):
            for j, dj in enumerate(drones):
                if j <= i:
                    continue
                if di.team == dj.team:
                    continue
                dist = np.linalg.norm(di.position - dj.position)
                if dist < self.d_safe:
                    violators.append((di.id, dj.id, dist))
        return len(violators) > 0, {"violators": violators}


class IntraTeamSafetyDistance(Constraint):
    """队内安全距离（违反即判负）"""
    name = "intra_team_safety"

    def __init__(self, d_safe: float):
        self.d_safe = d_safe

    def check(self, drones, gates, field_cfg):
        violators = []
        for i, di in enumerate(drones):
            for j, dj in enumerate(drones):
                if j <= i:
                    continue
                if di.team != dj.team:
                    continue
                dist = np.linalg.norm(di.position - dj.position)
                if dist < self.d_safe:
                    violators.append((di.id, dj.id, dist))
        return len(violators) > 0, {"violators": violators}


class GateFrameCollision(Constraint):
    """撞门框约束：无人机靠近门平面但未落在门框内即视为撞门"""
    name = "gate_collision"

    def __init__(self, drone_radius: float):
        self.drone_radius = drone_radius

    def check(self, drones, gates, field_cfg):
        hits = []
        for d in drones:
            p = d.position
            for g in gates:
                # 距门平面距离
                plane_dist = abs(np.dot(p - g.center, g.normal))
                if plane_dist > self.drone_radius:
                    continue
                local = p - g.center
                u = np.dot(local, g.tangent_h)
                v = np.dot(local, g.tangent_v)
                # 在门外延伸的"框墙"区域：靠近平面但 (u,v) 在框边附近
                near_frame_u = abs(u) > g.width / 2 - self.drone_radius and abs(u) < g.width / 2 + self.drone_radius
                near_frame_v = abs(v) > g.height / 2 - self.drone_radius and abs(v) < g.height / 2 + self.drone_radius
                outside_box = abs(u) > g.width / 2 or abs(v) > g.height / 2
                if outside_box and (near_frame_u or near_frame_v):
                    # 严格判定：贴近门平面 + 在框边/外
                    hits.append((d.id, g.id))
        return len(hits) > 0, {"hits": hits}


class FieldBoundary(Constraint):
    """场地边界约束"""
    name = "out_of_bounds"

    def check(self, drones, gates, field_cfg):
        outs = []
        for d in drones:
            x, y, z = d.position
            if not (field_cfg.x_range[0] <= x <= field_cfg.x_range[1] and
                    field_cfg.y_range[0] <= y <= field_cfg.y_range[1] and
                    field_cfg.z_range[0] <= z <= field_cfg.z_range[1]):
                outs.append(d.id)
        return len(outs) > 0, {"outs": outs}


def build_default_constraints(cfg) -> List[Constraint]:
    """根据配置生成默认约束列表"""
    return [
        InterTeamSafetyDistance(cfg.drone.inter_team_safe_dist),
        IntraTeamSafetyDistance(cfg.drone.intra_team_safe_dist),
        GateFrameCollision(cfg.drone.safety_radius),
        FieldBoundary(),
    ]
