"""
动力学模块
通过抽象基类封装，便于后续替换为四旋翼、固定翼等更复杂模型
"""
from abc import ABC, abstractmethod
import numpy as np


class DynamicsModel(ABC):
    """动力学抽象接口"""

    @property
    @abstractmethod
    def state_dim(self) -> int: ...

    @property
    @abstractmethod
    def action_dim(self) -> int: ...

    @abstractmethod
    def step(self, state: np.ndarray, action: np.ndarray, dt: float) -> np.ndarray:
        """单步前向积分，返回下一时刻状态"""
        ...

    @abstractmethod
    def get_position(self, state: np.ndarray) -> np.ndarray:
        """从状态中提取位置 (3,)"""
        ...

    @abstractmethod
    def get_velocity(self, state: np.ndarray) -> np.ndarray:
        """从状态中提取速度 (3,)"""
        ...


class DoubleIntegrator3D(DynamicsModel):
    """
    3D 双积分器质点模型
    state = [x, y, z, vx, vy, vz]   shape = (6,)
    action = [ax, ay, az]            shape = (3,)，受 max_accel 约束
    速度受 max_speed 约束（饱和裁剪）
    """

    def __init__(self, max_speed: float, max_accel: float):
        self.max_speed = max_speed
        self.max_accel = max_accel

    @property
    def state_dim(self) -> int:
        return 6

    @property
    def action_dim(self) -> int:
        return 3

    def step(self, state: np.ndarray, action: np.ndarray, dt: float) -> np.ndarray:
        pos = state[:3]
        vel = state[3:]

        # 控制量裁剪
        a_norm = np.linalg.norm(action)
        if a_norm > self.max_accel:
            action = action * (self.max_accel / (a_norm + 1e-9))

        # 半隐式欧拉积分
        new_vel = vel + action * dt
        v_norm = np.linalg.norm(new_vel)
        if v_norm > self.max_speed:
            new_vel = new_vel * (self.max_speed / (v_norm + 1e-9))
        new_pos = pos + new_vel * dt

        return np.concatenate([new_pos, new_vel]).astype(np.float32)

    def get_position(self, state: np.ndarray) -> np.ndarray:
        return state[:3].copy()

    def get_velocity(self, state: np.ndarray) -> np.ndarray:
        return state[3:].copy()


class DampedDoubleIntegrator3D(DoubleIntegrator3D):
    """
    带线性阻尼的双积分器。
    动作仍是 3D 加速度，但速度会按 drag 衰减，适合模拟更重、更稳的机型。
    """

    def __init__(self, max_speed: float, max_accel: float, drag: float = 0.1):
        super().__init__(max_speed=max_speed, max_accel=max_accel)
        self.drag = max(0.0, float(drag))

    def step(self, state: np.ndarray, action: np.ndarray, dt: float) -> np.ndarray:
        pos = state[:3]
        vel = state[3:]

        a_norm = np.linalg.norm(action)
        if a_norm > self.max_accel:
            action = action * (self.max_accel / (a_norm + 1e-9))

        damping = max(0.0, 1.0 - self.drag * dt)
        new_vel = (vel + action * dt) * damping
        v_norm = np.linalg.norm(new_vel)
        if v_norm > self.max_speed:
            new_vel = new_vel * (self.max_speed / (v_norm + 1e-9))
        new_pos = pos + new_vel * dt
        return np.concatenate([new_pos, new_vel]).astype(np.float32)


def build_dynamics(model_name: str, max_speed: float, max_accel: float, drag: float = 0.0) -> DynamicsModel:
    """按配置名创建动力学模型。"""
    if model_name == "double_integrator":
        return DoubleIntegrator3D(max_speed=max_speed, max_accel=max_accel)
    if model_name == "damped_double_integrator":
        return DampedDoubleIntegrator3D(max_speed=max_speed, max_accel=max_accel, drag=drag)
    raise ValueError(f"未知动力学模型: {model_name}")
