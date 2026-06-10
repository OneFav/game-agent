"""
实体定义：Drone（同构本体 + 角色标签） 和 Gate
"""
from enum import Enum
from dataclasses import dataclass
import numpy as np
from game_agent.envs.swarm_combat.dynamics import DynamicsModel


class Team(Enum):
    RED = 0
    BLUE = 1


class Role(Enum):
    RACER = 0       # 赛道任务
    DEFENDER = 1    # 阻拦/保护


class Drone:
    """
    所有无人机使用同一套物理参数和同一个类
    role 仅作为任务标签，影响奖励和策略目标，不影响动力学
    """

    def __init__(
        self,
        drone_id: int,
        team: Team,
        role: Role,
        dynamics: DynamicsModel,
        init_state: np.ndarray,
        safety_radius: float,
    ):
        self.id = drone_id
        self.team = team
        self.role = role
        self.dynamics = dynamics
        self.state = init_state.astype(np.float32).copy()
        self.safety_radius = safety_radius

        # 运行时记录
        self.alive = True
        self.score = 0.0          # 累计该机贡献分数（团队分由环境聚合）
        self.gate_pass_count = 0

    @property
    def position(self) -> np.ndarray:
        return self.dynamics.get_position(self.state)

    @property
    def velocity(self) -> np.ndarray:
        return self.dynamics.get_velocity(self.state)

    def step(self, action: np.ndarray, dt: float):
        self.state = self.dynamics.step(self.state, action, dt)


class Gate:
    """
    门：用中心点、法向量、宽高定义一个矩形穿越平面
    """

    def __init__(
        self,
        gate_id: int,
        center,
        normal,
        width,
        height,
        cooldown_steps,
        pass_direction: str = "team_forward",
    ):
        self.id = gate_id
        self.center = np.asarray(center, dtype=np.float32)
        self.normal = np.asarray(normal, dtype=np.float32)
        self.normal /= (np.linalg.norm(self.normal) + 1e-9)
        self.width = width
        self.height = height
        self.cooldown_steps = cooldown_steps
        self.pass_direction = pass_direction

        # 构造门平面的两个切向轴（水平 + 竖直）
        # 水平切向：法向与世界 z 轴叉乘
        z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        tangent_h = np.cross(self.normal, z_axis)
        if np.linalg.norm(tangent_h) < 1e-6:
            tangent_h = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        self.tangent_h = tangent_h / np.linalg.norm(tangent_h)
        self.tangent_v = np.cross(self.normal, self.tangent_h)
        self.tangent_v /= np.linalg.norm(self.tangent_v)

        # 冷却倒计时（按穿越者团队分别记录）
        self.cooldown_remaining = {Team.RED: 0, Team.BLUE: 0}

    def tick_cooldown(self):
        for k in self.cooldown_remaining:
            if self.cooldown_remaining[k] > 0:
                self.cooldown_remaining[k] -= 1

    def is_on_cooldown(self, team: Team) -> bool:
        return self.cooldown_remaining[team] > 0

    def trigger_cooldown(self, team: Team):
        self.cooldown_remaining[team] = self.cooldown_steps

    def check_pass(self, prev_pos: np.ndarray, curr_pos: np.ndarray, team: Team = None):
        """
        判断一架无人机本步是否穿过门
        方法：检查线段 prev_pos -> curr_pos 是否与门平面相交且交点落在矩形门框内
        返回 (passed: bool, intersection: np.ndarray or None)
        """
        d_prev = float(np.dot(prev_pos - self.center, self.normal))
        d_curr = float(np.dot(curr_pos - self.center, self.normal))

        # 同号：未穿过门平面
        if d_prev * d_curr > 0:
            return False, None
        if abs(d_curr - d_prev) < 1e-9:
            return False, None

        # 求交点参数 t
        t = d_prev / (d_prev - d_curr)
        if t < 0 or t > 1:
            return False, None
        intersection = prev_pos + t * (curr_pos - prev_pos)

        # 检查交点是否在矩形门框内
        local = intersection - self.center
        u = np.dot(local, self.tangent_h)
        v = np.dot(local, self.tangent_v)
        if abs(u) <= self.width / 2 and abs(v) <= self.height / 2:
            if self._direction_allowed(d_prev, d_curr, team):
                return True, intersection
        return False, None

    def check_intersection(self, prev_pos: np.ndarray, curr_pos: np.ndarray):
        """只判断是否穿过门矩形区域，不检查方向；便于调试和记录。"""
        d_prev = float(np.dot(prev_pos - self.center, self.normal))
        d_curr = float(np.dot(curr_pos - self.center, self.normal))
        if d_prev * d_curr > 0 or abs(d_curr - d_prev) < 1e-9:
            return False, None
        t = d_prev / (d_prev - d_curr)
        if t < 0 or t > 1:
            return False, None
        intersection = prev_pos + t * (curr_pos - prev_pos)
        local = intersection - self.center
        u = np.dot(local, self.tangent_h)
        v = np.dot(local, self.tangent_v)
        if abs(u) <= self.width / 2 and abs(v) <= self.height / 2:
            return True, intersection
        return False, None

    def _direction_allowed(self, d_prev: float, d_curr: float, team: Team = None) -> bool:
        direction = d_curr - d_prev
        if self.pass_direction == "bidirectional":
            return True
        if self.pass_direction == "positive":
            return direction > 0
        if self.pass_direction == "negative":
            return direction < 0
        if self.pass_direction == "team_forward":
            if team == Team.RED:
                return direction > 0
            if team == Team.BLUE:
                return direction < 0
            return True
        raise ValueError(f"未知穿门方向配置: {self.pass_direction}")
