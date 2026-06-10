# 模板代码说明

> **目标读者**：scenario_compiler 和 policy_designer 两个 Codex subagent。
> **用途**：帮助 Agent 理解当前可用的参考代码、模板选择策略和关键接口约束。

---

## 1. 总览：模板体系图

```
用户自然语言描述
        │
        ▼
┌─────────────────────────────────────────────────┐
│  scenario_compiler agent                        │
│  根据任务复杂度选择环境模板：                      │
│                                                 │
│  ┌─ 简单任务 (2 agent, 简单几何)                  │
│  │  → drone_ring_game 模板 (内联 env.py)         │
│  │                                              │
│  └─ 复杂任务 (N vs N, 3D, 多门, 编队)             │
│     → swarm_combat 模板 (导入 src/ 参考模块)       │
└─────────────────────────────────────────────────┘
        │ 产出 scenarios/<task_id>/
        ▼
┌─────────────────────────────────────────────────┐
│  policy_designer agent                          │
│  根据场景复杂度选择策略模板：                      │
│                                                 │
│  ┌─ 简单场景 (2D 点质量, 2 agent)                │
│  │  → RuleRingNavigationPolicy 模板              │
│  │                                              │
│  └─ 复杂场景 (3D 多智能体, 编队/护航)              │
│     → SafeRulePolicyAdapter 模板                 │
└─────────────────────────────────────────────────┘
        │ 产出 policies/<policy_id>/
        ▼
┌─────────────────────────────────────────────────┐
│  experiment_autoresearch agent                  │
│  对冻结场景+策略执行确定性 sweep                   │
└─────────────────────────────────────────────────┘
```

---

## 2. 环境模板（给 scenario_compiler 看）

### 2.1 参考代码位置

| 环境 | 路径 | 类型 |
|------|------|------|
| **drone_ring_game** | `src/game_agent/envs/drone_ring_game/env.py` | 参考实现（155 行，单块 2D） |
| **swarm_combat** | `src/game_agent/envs/swarm_combat/` | 参考模块（12 个文件，模块化 3D） |

### 2.2 何时用 drone_ring_game

**适用条件**：
- 只有 2 个智能体（红方 ×1 + 蓝方 ×1）
- 领域是 2D 平面（XY）
- 智能体动力学可以简化为双积分器
- 门（环）垂直于运动方向
- 不需要编队、护航、软避障等高级行为

**生成方式**：在内联模板字符串 `SCENARIO_ENV_PY` 中直接写入环境代码（完全自包含，不依赖 swarm_combat 模块）。

**模板位置**：`src/game_agent/scenario_compiler/templates.py` → `SCENARIO_ENV_PY`

### 2.3 何时用 swarm_combat

**适用条件**（满足任一项即可升级）：
- 智能体数量 > 2（N vs N 编队对抗）
- 需要 3D 空间（XYZ）
- 需要多种门布局（slalom / wide_slalom / vertical_wave / figure_eight）
- 需要赛车机 + 防守机双角色（RACER / DEFENDER）
- 需要编队紧密奖励、拦截奖励、保护奖励等组合奖励
- 需要队间/队内安全距离、门框碰撞、边界约束等多层约束

**生成方式**：生成一个薄配置层 `env.py`，导入 `game_agent.envs.swarm_combat` 模块并配置参数。

**模板位置**：`src/game_agent/scenario_compiler/templates.py` → `SWARM_COMBAT_ENV_PY`

**生成的 env.py 示例**：
```python
"""scenarios/<task_id>/env.py -- 由 scenario_compiler 生成"""
import numpy as np
from game_agent.envs.swarm_combat import EnvConfig, SwarmCombatEnv

def make_env(config: dict | None = None) -> SwarmCombatEnv:
    cfg = EnvConfig()
    cfg = cfg.with_updates(
        max_steps=config.get("max_steps", 600),
        n_red=config.get("n_red", 4),
        n_blue=config.get("n_blue", 4),
        n_red_racers=config.get("n_red_racers", 2),
        n_blue_racers=config.get("n_blue_racers", 2),
        rewards__gate_pass=config.get("gate_pass_reward", 1.0),
    )
    cfg = cfg.set_gate_layout(config.get("gate_layout", "slalom"))
    return SwarmCombatEnv(cfg)
```

### 2.4 关键接口约束

以下约束是**必须遵守**的，无论使用哪种模板：

#### reset(seed) 接口
```python
def reset(self, seed: int | None = None) -> tuple[dict, dict]:
    """返回 (obs_dict, info_dict)。
    - obs_dict: {agent_id: np.ndarray} 每个智能体的观测
    - info_dict: {} （可为空）
    - seed 为 None 时使用内部随机状态；非 None 时用该 seed 重置随机生成器
    - 相同 seed 必须产生完全相同的初始状态（确定性）
    """
```

#### step(actions) 接口
```python
def step(self, actions: dict) -> tuple[dict, dict, dict, dict, dict]:
    """返回 (obs, rewards, terminated, truncated, info)。
    - obs: {agent_id: np.ndarray}
    - rewards: {agent_id: float}
    - terminated: {agent_id: bool}   # 终止（碰撞/目标达成）
    - truncated: {agent_id: bool}    # 截断（超时）
    - info: {agent_id: dict}         # 每个智能体的附加信息
    """
```

#### 观测空间约束
- 每个智能体的观测必须是**固定长度**的 `np.ndarray`（shape 在 task_spec.yaml 中声明）
- 不能包含变长数据（如 Python list/dict）
- 浮点类型：`np.float32`

#### 动作空间约束
- 每个智能体的动作必须是**固定长度**的 `np.ndarray`
- 动作范围在 task_spec.yaml 的 `action_space.low` / `action_space.high` 中声明
- 环境内部可以 clip 动作到合法范围，但不应默默缩放（应记录到 info）

#### 评估指标独立性
- `evaluation_metrics.primary.name` **不能**与 `reward_structure.components[*].name` 中任何名称相同
- 这是因为 reward 是训练信号，evaluation_metrics 是评价标准——两者必须独立

### 2.5 swarm_combat 子模块速查

| 子模块 | 路径 | 导出关键符号 |
|--------|------|-------------|
| **config** | `swarm_combat/config.py` | `EnvConfig`, `FieldConfig`, `GateConfig`, `DroneConfig`, `RuleConfig`, `RewardWeights`, `SpawnConfig` |
| **entities** | `swarm_combat/entities.py` | `Drone`, `Gate`, `Team`(RED/BLUE), `Role`(RACER/DEFENDER) |
| **dynamics** | `swarm_combat/dynamics.py` | `DynamicsModel`(ABC), `DoubleIntegrator3D`, `DampedDoubleIntegrator3D`, `build_dynamics()` |
| **constraints** | `swarm_combat/constraints.py` | `Constraint`(ABC), `InterTeamSafetyDistance`, `IntraTeamSafetyDistance`, `GateFrameCollision`, `FieldBoundary` |
| **rewards** | `swarm_combat/rewards.py` | `RewardComponent`(ABC), `GatePassReward`, `FormationTightnessReward`, `InterceptionReward`, `ProtectionReward`, `SafetyViolationPenalty`, `CollisionPenalty`, `OutOfBoundsPenalty`, `TimePenalty` |
| **terminations** | `swarm_combat/terminations.py` | `TerminationCondition`(ABC), `MaxStepsTermination`, `TargetScoreTermination`, `CollisionTermination` |
| **evaluation** | `swarm_combat/evaluation.py` | `run_one_episode()`, `run_experiment()`, `summarize_results()`, `ExperimentRecorder` |
| **visualizer** | `swarm_combat/visualizer.py` | `render_animation()`, `render_snapshot()`, `save_trajectory_figure()`, `save_topdown_figure()` |
| **rl_wrapper** | `swarm_combat/rl_wrapper.py` | `SwarmCombatParallelEnv`（PettingZoo ParallelEnv 兼容层） |

### 2.6 swarm_combat 配置关键参数

#### 枚举值

| 参数 | 可选值 | 说明 |
|------|--------|------|
| `gate_layout` | `straight`, `slalom`, `wide_slalom`, `vertical_wave`, `figure_eight` | 门布局 |
| `pass_direction` | `team_forward`, `bidirectional`, `positive`, `negative` | 穿门方向限制 |
| `dynamics` | `double_integrator`, `damped_double_integrator` | 动力学模型 |
| `spawn_mode` | `fixed`, `random` | 出生模式 |
| `defender_mode` | `escort`, `intercept` | 防守机行为模式 |

#### 数值范围

| 参数 | 典型范围 | 单位 |
|------|----------|------|
| `max_speed` | 0.5 ~ 20.0 | m/s |
| `max_accel` | 0.5 ~ 50.0 | m/s² |
| `safety_radius` | 0.3 ~ 3.0 | m |
| `dt` | 0.02 ~ 0.1 | s |
| `max_steps` | 200 ~ 2000 | step |
| `gate_pass_reward` | 0.5 ~ 5.0 | 无量纲 |

---

## 3. 策略模板（给 policy_designer 看）

### 3.1 参考代码位置

| 策略 | 路径 | 类型 |
|------|------|------|
| **RuleRingNavigationPolicy** | `src/game_agent/policy_designer/templates.py` | 内联模板（661 行） |
| **SafeRulePolicy** | `src/game_agent/policy_designer/reference_policies/safe_rule_policy.py` | 参考实现（386 行） |
| **SafeRulePolicyAdapter** | `src/game_agent/policy_designer/reference_policies/__init__.py` | Policy ABC 适配器 |

### 3.2 何时用 RuleRingNavigationPolicy

**适用条件**：
- 场景是 2D 点质量模型（drone_ring_game）
- 仅 2 个智能体
- 策略逻辑简单：红方导航至门，蓝方拦截红方
- 不需要多智能体协作/竞争逻辑

**生成方式**：内联模板 `POLICY_PY` 直接生成 `RuleRingNavigationPolicy` 类（完全自包含）。

### 3.3 何时用 SafeRulePolicyAdapter

**适用条件**（满足任一项即可升级）：
- 场景是 3D swarm_combat 环境
- 多个智能体（N vs N）
- 需要多航道分配（多个赛车机同时穿门）
- 需要护航/拦截双模式
- 需要前视风险检查 + 刹车机制

**生成方式**：模板 `SWARM_RULE_POLICY_PY` 生成导入 `reference_policies` 的策略代码。

**生成的 policy.py 示例**：
```python
"""policies/<policy_id>/policy.py -- 由 policy_designer 生成"""
import numpy as np
from contracts.policy_protocol import Policy
from game_agent.policy_designer.reference_policies import SafeRulePolicyAdapter as PolicyClass
```

### 3.4 Policy ABC 必须实现的接口

```python
class Policy(ABC):
    @abstractmethod
    def reset(self, seed: int) -> None:
        """重置策略状态。相同 seed 必须产生完全相同的策略行为。"""
        ...

    @abstractmethod
    def act(self, obs, agent_id, info=None) -> np.ndarray:
        """返回单个智能体的动作。
        - obs: np.ndarray 或 dict（取决于环境）
        - agent_id: str 或 int
        - 返回值: np.ndarray，必须在 [action_space.low, action_space.high] 范围内
        - 必须使用 np.clip() 确保动作不越界
        """
        ...

    @abstractmethod
    def load(self, checkpoint_path: str) -> None:
        """加载训练好的权重。规则策略可为空操作（pass）。"""
        ...

    @abstractmethod
    def get_config_schema(self) -> dict:
        """返回配置参数的 JSON Schema。
        格式: {param_name: {type: str, default: Any, min: num, max: num, enum: [...]}}
        search_space.yaml 中的每个参数必须出现在此返回值中。
        """
        ...

    def supports_training(self) -> bool:
        """是否需要训练。规则策略返回 False。"""
        return True

    def get_diagnostics(self) -> dict:
        """可选的诊断信息。"""
        return {}
```

### 3.5 动作安全约束（红线）

1. **Bound clip**：所有 `act()` 返回值必须 `np.clip(action, low, high)`
2. **纯函数**：`act()` 不能有副作用（不能 print、写文件、修改全局状态）
3. **确定性**：`reset(seed) + act(obs)` 必须可复现（相同 seed 相同输出）
4. **零动作兜底**：遇到任何异常返回 `np.zeros(action_dim)`，不抛异常
5. **延迟限制**：单次 `act()` 延迟 < 50ms（CPU）

### 3.6 train.py / infer.py CLI 签名

`train.py`：
```bash
python policies/<policy_id>/train.py \
  --config <path> --scenario <path> --seed <int> \
  --output_dir <path> --max_steps <int> --wall_time_limit <int> \
  [--resume_from <path>] [--log_interval <int>]
```
退出码：0=成功, 1=参数错误, 2=不收敛, 3=资源不足

`infer.py`：
```bash
python policies/<policy_id>/infer.py \
  --checkpoint <path> --scenario <path> --eval_seeds <list> \
  --output <path> [--render] [--stress_test <name>]
```
输出 `eval_results.json`：`{metrics: {primary, secondary, hard_constraints}, per_seed_metrics: [...], failure_episodes: [...]}`

### 3.7 SafeRulePolicy 的关键参数

| 参数 | 默认值 | 作用 |
|------|--------|------|
| `desired_speed` | 4.0 | 目标巡航速度 |
| `position_gain` | 1.2 | 位置误差增益（向目标点靠拢的强度） |
| `velocity_gain` | 2.2 | 速度误差增益（速度对齐的强度） |
| `risk_margin` | 0.6 | 碰撞风险判定距离（m） |
| `boundary_margin` | 1.2 | 边界回推触发距离（m） |
| `turn_steps` | 12 | 转向平滑步数 |
| `turn_lookahead` | 5.0 | 前瞻距离（用于穿越目标点计算） |
| `risk_lookahead_steps` | 18 | 碰撞前向预测步数 |
| `brake_release_speed` | 0.35 | 刹车释放阈值（m/s，低于此速恢复导航） |
| `defender_mode` | "escort" | 防守机模式：escort（护航己方）或 intercept（拦截对方） |

---

## 4. 共享合约（两个 Agent 都必须遵守）

### 4.1 contracts/policy_protocol.py

**路径**：`src/contracts/policy_protocol.py`

**绝对禁止修改**。定义了 `Policy` ABC，所有策略包必须实现该接口。

### 4.2 contracts/scenario_schema.yaml

**路径**：`src/contracts/scenario_schema.yaml`

**绝对禁止修改**。定义了场景包的 11 个必需字段：
`schema_version`, `task_id`, `task_family`, `formalism`, `agents`, `observation_space`, `action_space`, `reward_structure`, `evaluation_metrics`, `termination_conditions`, `splits`

`task_family` 枚举当前仅含 `drone_ring_game`。如需新增 swarm_combat 任务族，需先在此 schema 的 `task_family.enum` 中添加 `swarm_combat`。

### 4.3 接口合同文档

| 文档 | 路径 | 内容 |
|------|------|------|
| Interface Contract 1 | `INTERFACE_1_SCENARIO_TO_POLICY.md` | 场景包完整 schema，供 policy_designer 和 autoresearch 消费 |
| Interface Contract 2 | `INTERFACE_2_POLICY_TO_AUTORESEARCH.md` | 策略包完整 schema，供 autoresearch 消费 |

---

## 5. 工作边界矩阵（红线）

| 操作 | scenario_compiler | policy_designer | experiment_autoresearch |
|------|:--:|:--:|:--:|
| 写 `scenarios/<task_id>/` | ✅ | ❌ | ❌ |
| 写 `policies/<policy_id>/` | ❌ | ✅ | ❌ |
| 写 `experiments/<exp_id>/` | ❌ | ❌ | ✅ |
| 修改 `src/contracts/` | ❌ | ❌ | ❌ |
| 修改 `src/hooks/` | ❌ | ❌ | ❌ |
| 修改 `src/game_agent/` | ❌ | ❌ | ❌ |
| 读取 `src/game_agent/envs/` (只读) | ✅ | ✅ | ✅ |
| 读取 `reference_policies/` (只读) | ❌ | ✅ | ✅ |

---

## 6. 常见问题

### Q: 生成的 env.py 应该内联还是导入？
- 简单场景（drone_ring_game）→ 内联（自包含，不依赖外部模块）
- 复杂场景（swarm_combat）→ 导入式（薄配置层 + `from game_agent.envs.swarm_combat import ...`）

### Q: SafeRulePolicy 为什么不直接实现 Policy ABC？
因为 SafeRulePolicy 使用 `compute_actions(env)` 批量模式，需要完整的 `env` 对象访问（所有无人机状态、门状态），而 Policy ABC 使用 `act(obs, agent_id)` 单智能体模式，仅接收观测向量。两种抽象层次根本不同。通过 `SafeRulePolicyAdapter` 桥接。

### Q: 何时应该在 task_spec.yaml 中新增 task_family？
当用户任务的动力学、观测空间、动作空间或评估逻辑与现有 `drone_ring_game` 有本质不同时（如 3D 空间、多智能体编队、新博弈类型），需要新增 task_family（如 `swarm_combat`）。这需要先修改 `contracts/scenario_schema.yaml` 的 task_family 枚举。

### Q: 任务的 evaluation_metrics 如何选择 primary metric？
- drone_ring_game：`success_rate`（红方成功穿环比例）
- swarm_combat：`team_score`（团队累计得分）或 `win_rate`（胜率）
- primary metric 不能与任何 reward component 同名

### Q: 环境必须包含哪些 hard_constraints？
至少包含一个约束。推荐：`collision_rate`（碰撞率）。swarm_combat 环境还推荐：`out_of_bounds_rate`（出界率）、`action_violation_rate`（动作违规率）。
