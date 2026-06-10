"""
集群对抗仿真环境 - 配置参数
所有可调参数集中在此，便于实验调参
"""
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


RED_RANDOM_X_RANGE = (-21.0, -19.0)
BLUE_RANDOM_X_RANGE = (19.0, 21.0)


@dataclass
class FieldConfig:
    """场地配置"""
    x_range: Tuple[float, float] = (-25.0, 25.0)
    y_range: Tuple[float, float] = (-25.0, 25.0)
    z_range: Tuple[float, float] = (0.5, 15.0)


@dataclass
class GateConfig:
    """单个门的配置"""
    center: np.ndarray            # 门中心 (3,)
    normal: np.ndarray            # 门法向量 (3,)，单位向量
    width: float = 2.0
    height: float = 2.0
    cooldown_steps: int = 30
    # bidirectional: 两个方向均可计分
    # team_forward: 红方沿 normal 正向穿越计分，蓝方沿 normal 反向穿越计分
    # positive / negative: 仅允许沿 normal 正向 / 反向计分
    pass_direction: str = "team_forward"


@dataclass
class DroneConfig:
    """无人机本体参数（红蓝同构）"""
    mass: float = 1.0
    max_speed: float = 8.0
    max_accel: float = 10.0
    safety_radius: float = 0.5
    inter_team_safe_dist: float = 0.8
    intra_team_safe_dist: float = 0.6


@dataclass
class DroneTypeConfig:
    """不同机型动力学参数，可按角色或队伍挂载。"""
    dynamics: str = "double_integrator"  # double_integrator / damped_double_integrator
    max_speed: Optional[float] = None
    max_accel: Optional[float] = None
    drag: float = 0.0


@dataclass
class RuleConfig:
    """胜负和终止规则配置。"""
    target_score: Optional[float] = None
    collision_ends_episode: bool = True
    out_of_bounds_ends_episode: bool = True
    draw_tolerance: float = 1e-6


@dataclass
class RewardWeights:
    """奖励组件权重"""
    gate_pass: float = 10.0
    formation_tight: float = 5.0
    interception: float = 2.0
    protection: float = 1.0
    safety_violation: float = -0.5
    collision: float = -100.0
    out_of_bounds: float = -100.0
    time_penalty: float = -0.01


def build_gate_layout(layout: str = "slalom") -> List[GateConfig]:
    """生成常用门布局。"""
    layout = layout.lower()
    gates = []
    if layout == "straight":
        centers = [(-14, 0, 4), (-7, 0, 4), (0, 0, 4), (7, 0, 4), (14, 0, 4)]
    elif layout == "wide_slalom":
        centers = [(-15, -6, 4), (-9, 5, 5), (-3, -5, 4), (3, 5, 6), (9, -5, 4), (15, 6, 5)]
    elif layout == "vertical_wave":
        centers = [(-14, -3, 3), (-8, 3, 6), (-2, -3, 4), (4, 3, 7), (10, -3, 5), (16, 3, 4)]
    elif layout == "figure_eight":
        centers = [(-12, -5, 4), (-6, 0, 5), (0, 5, 4), (6, 0, 5), (12, -5, 4), (0, 0, 6)]
    elif layout == "slalom":
        centers = [(-12, 0, 4), (-6, 4, 5), (0, -4, 4), (6, 4, 6), (12, 0, 4)]
    else:
        raise ValueError(f"未知门布局: {layout}")

    for c in centers:
        gates.append(GateConfig(
            center=np.array(c, dtype=np.float32),
            normal=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            width=3.0, height=3.0, cooldown_steps=30,
            pass_direction="team_forward",
        ))
    return gates


def _default_gates() -> List[GateConfig]:
    """默认 slalom 门布局。"""
    return build_gate_layout("slalom")


@dataclass
class SpawnConfig:
    """
    起飞初始化配置
    mode: "fixed" 或 "random"
        - fixed:  按 fixed_positions 列表精确放置（不足则用默认排布补齐）
        - random: 在指定 box 区域内随机采样位置
    """
    mode: str = "fixed"  # "fixed" / "random"

    # ===== fixed 模式参数 =====
    # 若为 None，则使用环境默认排布（沿 y 轴均匀排开）
    # 若提供，则按列表顺序对应每架无人机：[(x,y,z), (x,y,z), ...]
    fixed_positions: list = None

    # ===== random 模式参数 =====
    # 在该 box 内均匀采样
    # 若为 None，EnvConfig 会按队伍自动补齐：
    # 红方 RED_RANDOM_X_RANGE，蓝方 BLUE_RANDOM_X_RANGE
    random_x_range: Optional[Tuple[float, float]] = None
    random_y_range: Tuple[float, float] = (-8.0, 8.0)
    random_z_range: Tuple[float, float] = (3.0, 6.0)

    # 随机模式下生成的位置之间的最小间距（避免初始就违反队内安全距离）
    min_separation: float = 1.5
    # 重采样最大尝试次数
    max_resample_tries: int = 200


def _apply_team_spawn_defaults(spawn_cfg: SpawnConfig, team: str) -> None:
    """给未显式改 x 范围的随机出生配置补上队伍侧默认值。"""
    default_x_range = RED_RANDOM_X_RANGE if team == "red" else BLUE_RANDOM_X_RANGE
    if spawn_cfg.random_x_range is None:
        spawn_cfg.random_x_range = default_x_range


@dataclass
class EnvConfig:
    """环境总配置"""
    # 仿真参数
    dt: float = 0.05
    max_steps: int = 600

    # 双方数量（完全可配置）
    n_red: int = 4
    n_red_racers: int = 2
    n_blue: int = 4
    n_blue_racers: int = 2

    # 子模块配置
    field: FieldConfig = dc_field(default_factory=FieldConfig)
    drone: DroneConfig = dc_field(default_factory=DroneConfig)
    rules: RuleConfig = dc_field(default_factory=RuleConfig)
    rewards: RewardWeights = dc_field(default_factory=RewardWeights)
    gates: List[GateConfig] = dc_field(default_factory=_default_gates)
    gate_layout: str = "slalom"

    # 机型参数；未设置的 max_speed / max_accel 会回退到 drone 中的全局值
    drone_types: Dict[str, DroneTypeConfig] = dc_field(default_factory=lambda: {
        "racer": DroneTypeConfig(dynamics="double_integrator", max_speed=8.0, max_accel=10.0),
        "defender": DroneTypeConfig(dynamics="damped_double_integrator", max_speed=6.0, max_accel=8.0, drag=0.15),
    })

    # 红蓝双方独立的初始化配置
    spawn_red: SpawnConfig = dc_field(default_factory=lambda: SpawnConfig(
        mode="fixed",
        random_x_range=RED_RANDOM_X_RANGE,
        random_y_range=(-8.0, 8.0),
        random_z_range=(3.0, 6.0),
    ))
    spawn_blue: SpawnConfig = dc_field(default_factory=lambda: SpawnConfig(
        mode="fixed",
        random_x_range=BLUE_RANDOM_X_RANGE,
        random_y_range=(-8.0, 8.0),
        random_z_range=(3.0, 6.0),
    ))

    # 随机种子
    seed: int = 42

    def __post_init__(self):
        _apply_team_spawn_defaults(self.spawn_red, "red")
        _apply_team_spawn_defaults(self.spawn_blue, "blue")

    def set_gate_layout(self, layout: str):
        """切换预设门布局并返回自身，方便链式调参。"""
        self.gate_layout = layout
        self.gates = build_gate_layout(layout)
        return self

    def with_updates(self, **updates: Any):
        """
        便捷修改配置参数，支持用双下划线访问嵌套字段。

        示例：
            cfg = EnvConfig().with_updates(
                max_steps=1000,
                drone__max_speed=12.0,
                rewards__gate_pass=20.0,
                spawn_red__mode="random",
                spawn_blue__mode="random",
                spawn_blue__random_x_range=(18.0, 22.0),
            )
        """
        layout_update = updates.pop("gate_layout", None)
        if layout_update is not None:
            self.set_gate_layout(layout_update)

        for key, value in updates.items():
            target = self
            parts = key.split("__")
            for part in parts[:-1]:
                if not hasattr(target, part):
                    raise AttributeError(f"未知配置字段: {key}")
                target = getattr(target, part)
            field_name = parts[-1]
            if not hasattr(target, field_name):
                raise AttributeError(f"未知配置字段: {key}")
            setattr(target, field_name, value)

        _apply_team_spawn_defaults(self.spawn_red, "red")
        _apply_team_spawn_defaults(self.spawn_blue, "blue")
        return self

