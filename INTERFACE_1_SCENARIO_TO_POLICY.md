# Interface Contract 1: ScenarioSpec
## 场景编译 Agent → 策略设计 Agent

> **本文档是合同，不是文档。** 一旦 v1.0 冻结,任何字段含义、格式、命名的修改都必须开新版本号,并在 `CHANGELOG.md` 记录。

---

## 0. 这份合同管什么

**生产方**:场景编译 Agent (Scenario Compiler)
**消费方**:策略设计 Agent (Policy Designer)、自动实验 Agent (AutoResearch)
**生命周期**:`pre_scenario_compile` → 编译 → `post_scenario_compile` 校验 → 冻结 → 下游消费

> **下游约定**:策略设计 Agent 通过本合同消费场景;自动实验 Agent **只读** `evaluation_metrics` 和 `splits` 两个字段(用于 promotion gate),不读 `reward_structure`(防止 reward hacking)。

---

## 1. 物理交付物 (Deliverables)

每个场景必须以**目录**形式交付,目录名 = `task_id`。

```
scenarios/<task_id>/
├── task_spec.yaml          [必需] 形式化任务定义,本合同的核心
├── model.md                [必需] POSG 形式化文档,人类可读
├── env_config.yaml         [必需] 环境实例化参数
├── env.py                  [必需] PettingZoo Parallel API 实现
├── tests/                  [必需] 场景级 contract tests
│   ├── test_reset_deterministic.py
│   ├── test_obs_action_shape.py
│   ├── test_termination.py
│   ├── test_collision_detection.py
│   ├── test_ring_crossing.py        # 任务族特定
│   ├── test_communication.py        # 当通信模式非 perfect 时必需
│   └── test_reward_components.py
├── assumptions.md          [必需] 自然语言中未明确、由 agent 补默认值的部分
└── manifest.json           [必需] 版本号 + freeze hash + 校验状态
```

**完整性约束**:目录中**所有文件必须同时存在**,缺一即视为合同违约,`post_scenario_compile.py` 直接 fail。

---

## 2. task_spec.yaml — 字段规范

### 2.1 顶层结构

```yaml
schema_version: "1.0"           # 必需,严格匹配 contracts/scenario_schema.yaml 版本
task_id: "drone_ring_001"       # 必需,全局唯一,小写 + 下划线 + 三位数字
task_family: "drone_ring_game"  # 必需,必须是 allowed_task_family 之一
formalism: "POSG"               # 必需,枚举: MDP | MarkovGame | POSG | Dec-POMDP
created_at: "2026-05-01T10:00:00Z"
created_by: "scenario_compiler/v0.3.1"
```

### 2.2 智能体定义 — `agents`

```yaml
agents:
  red:
    count: 1                    # 必需,整数
    role: "evader"              # 必需,枚举: evader | pursuer | blocker | goal_seeking | escort
    start_delay_s: 0.0          # 可选,默认 0.0
    init_position_distribution:
      type: "fixed" | "uniform" | "gaussian"
      params: { ... }
  blue:
    count: 1
    role: "pursuer"
    start_delay_s: 5.0
```

**约束**:`agents` 至少包含一个阵营,每个阵营 `count >= 1`。

### 2.3 观测空间 — `observation_space`

```yaml
observation_space:
  type: "Box"                   # 必需,枚举: Box | Dict | MultiBinary
  shape: [12]                   # 必需 (Box 类型)
  low:  [-10, -10, -5, -2, -2, -1, -10, -10, -5, -2, -2, -1]
  high: [ 10,  10,  5,  2,  2,  1,  10,  10,  5,  2,  2,  1]
  dtype: "float32"
  description: |
    维度含义(逐维标注,不可省):
    [0:3]   self_position (x, y, z)
    [3:6]   self_velocity (vx, vy, vz)
    [6:9]   relative_opponent_position
    [9:12]  relative_opponent_velocity
  partial_observability: true   # 必需,布尔
```

**约束**:`shape`、`low`、`high` 三者长度必须一致;`description` 必须逐维标注。

### 2.4 动作空间 — `action_space`

```yaml
action_space:
  type: "Box"
  shape: [4]
  low:  [-2, -2, -1, -1]
  high: [ 2,  2,  1,  1]
  dtype: "float32"
  semantics: "velocity_setpoint"  # 必需,枚举: velocity_setpoint | acceleration_setpoint | discrete_action
  description: |
    [0] vx (m/s)
    [1] vy (m/s)
    [2] vz (m/s)
    [3] yaw_rate (rad/s)
```

**约束**:`semantics` 与策略 agent 的 `action_type` 要求必须一致。

### 2.5 奖励结构 — `reward_structure` ⚠️ 仅训练用

```yaml
reward_structure:
  shaping: "dense"              # 枚举: dense | sparse
  components:
    - name: "ring_progress"
      weight: 1.0
      description: "穿过圆环的归一化进度"
    - name: "collision_penalty"
      weight: -10.0
      description: "发生碰撞时的一次性惩罚"
    - name: "energy_penalty"
      weight: -0.01
  
  notes: |
    ⚠️ 此 reward 仅用于训练优化。
    最终评价指标见 evaluation_metrics 字段,与 reward 完全独立。
    自动实验 Agent 严禁读取此字段作为评价依据。
```

**红线**:
- 策略 Agent 可以读 `reward_structure` 设计训练流程
- 自动实验 Agent **绝对不能**读 `reward_structure`
- 任何 agent 都**不能修改** `reward_structure` (修改需走回退路径)

### 2.6 终止条件 — `termination_conditions`

```yaml
termination_conditions:
  - type: "ring_passed"
    agent: "red"
    description: "红方穿过最后一个圆环"
  - type: "collision_any"
    description: "任意智能体发生碰撞"
  - type: "out_of_bounds"
    description: "任意智能体越界"
  - type: "timeout"
    steps: 1000
    description: "时间步达到上限 (truncation,非 termination)"
```

**约束**:必须区分 `terminated` (任务结束) 和 `truncated` (时间截断)。`env.py` 必须按 Gymnasium 规范返回这两个独立标志。

### 2.7 评价指标 — `evaluation_metrics` ⚠️ 自动实验 Agent 的核心入口

```yaml
evaluation_metrics:
  primary:
    name: "constrained_success_rate"
    direction: "maximize"
    promotion_threshold: 0.80   # 通过晋级门的最低值
    description: "穿过所有圆环且不违反硬约束的 episode 比例"
  
  secondary:
    - name: "avg_episode_length"
      direction: "minimize"
    - name: "path_length"
      direction: "minimize"
    - name: "control_smoothness"
      direction: "maximize"
  
  hard_constraints:
    - name: "collision_rate"
      max: 0.05
      description: "发生碰撞的 episode 比例上限"
    - name: "out_of_bounds_rate"
      max: 0.01
    - name: "action_violation_rate"
      max: 0.0
```

**约束**:
- `primary` 有且仅有一个
- `hard_constraints` 至少包含 `collision_rate`
- `direction` 必须是 `maximize` 或 `minimize`
- 这些指标的实现位于 `evaluator/`,**任何 agent 都不能改**

### 2.8 数据集划分 — `splits`

```yaml
splits:
  train_seeds: [0, 1, 2, ..., 99]       # 列表或区间表达式
  val_seeds:   [100, 101, ..., 119]
  hidden_test:
    path: "evaluator/hidden_tests.py"
    description: "实现细节对所有 agent 不可见,只能通过 evaluator 调用"
  stress_tests:
    - name: "high_wind"
      config_override: { wind_speed: 3.0 }
    - name: "comm_blackout"
      config_override: { communication.packet_loss_prob: 0.5 }
    - name: "adversarial_opponent"
      config_override: { opponent_policy: "adversarial_v1" }
```

**约束**:
- 三个 split 的 seed 集合必须**完全不相交**
- 自动实验 Agent 只能用 `train_seeds` 训练、`val_seeds` 调参
- `hidden_test` 只在最终报告中调用一次,不能用于优化决策

---

## 3. env.py — 编程接口

### 3.1 必须实现的 API

```python
from pettingzoo.utils.env import ParallelEnv

class DroneRingEnv(ParallelEnv):
    metadata = {
        "render_modes": ["human", "rgb_array"],
        "name": "drone_ring_001_v0",
    }
    
    def __init__(self, env_config: dict): ...
    
    def reset(
        self, 
        seed: int | None = None,
        options: dict | None = None,
    ) -> tuple[dict, dict]:
        """
        Returns:
            observations: {agent_id: np.ndarray}
            infos: {agent_id: dict}
        """
    
    def step(
        self,
        actions: dict[str, np.ndarray],
    ) -> tuple[dict, dict, dict, dict, dict]:
        """
        Returns:
            observations: {agent_id: obs}
            rewards: {agent_id: float}
            terminations: {agent_id: bool}    # 任务真正结束
            truncations: {agent_id: bool}     # 时间截断
            infos: {agent_id: dict}           # 必须包含 'collision', 'out_of_bounds' 等诊断字段
        """
    
    def observation_space(self, agent: str) -> gym.Space: ...
    def action_space(self, agent: str) -> gym.Space: ...
    def render(self) -> np.ndarray | None: ...
    def close(self) -> None: ...
```

### 3.2 `info` 字典必需字段

每个 step 返回的 `infos[agent_id]` 字典必须包含:

```python
{
    "collision": bool,              # 此 step 是否发生碰撞
    "out_of_bounds": bool,
    "ring_passed_count": int,       # 任务族特定字段
    "communication_dropped": bool,  # 当通信模式非 perfect 时必需
    "action_clipped": bool,         # 动作是否被 safety shield 裁剪
}
```

策略和实验 agent 都依赖这些字段做诊断,缺失即合同违约。

### 3.3 确定性约束

- `reset(seed=42)` 必须使两次运行得到**逐位相同**的 observation 序列
- `env.py` 不得使用未受 seed 控制的随机源 (`time.time()`、`os.urandom()` 等)

---

## 4. manifest.json — 冻结凭证

```json
{
  "schema_version": "1.0",
  "task_id": "drone_ring_001",
  "version": "1.0.0",
  "created_at": "2026-05-01T10:00:00Z",
  "frozen_at": "2026-05-01T10:15:23Z",
  "freeze_hash": "sha256:a3f2b8c91d7e...",
  "files": {
    "task_spec.yaml":   "sha256:b4c5...",
    "model.md":         "sha256:d6e7...",
    "env_config.yaml":  "sha256:f8a9...",
    "env.py":           "sha256:1011..."
  },
  "validation": {
    "schema_check": "passed",
    "contract_tests": { "passed": 7, "failed": 0, "skipped": 0 },
    "smoke_test": "passed"
  },
  "downstream_consumers": [
    "policies/*",
    "experiments/*"
  ]
}
```

**冻结规则**:`freeze_hash` 由 `post_scenario_compile.py` 计算并写入。一旦冻结,目录变为只读;如需修改,必须开新 `task_id`(如 `drone_ring_002`)或新版本号。

---

## 5. 校验流程 — `post_scenario_compile.py`

下游 agent 在消费场景前,必须确认这些检查全部通过:

```bash
# 1. Schema 校验
python hooks/post_scenario_compile.py --scenario scenarios/<task_id>

# 检查项:
# [✓] task_spec.yaml 字段完整且类型正确
# [✓] model.md 包含所有必需章节
# [✓] env.py 可以 import 且实例化
# [✓] env.reset(seed=0) 两次结果一致
# [✓] obs/action shape 与 task_spec 一致
# [✓] tests/ 全部通过
# [✓] info 字典包含必需字段
# [✓] manifest.json freeze_hash 与文件实际 hash 一致
# [✓] 无禁止字段(如直接修改 evaluator/ 的引用)
```

**任意一项失败 → 编译失败,不得交付下游。**

---

## 6. 版本演化规则

| 变更类型 | 版本号变化 | 是否需要消费方迁移 |
|---|---|---|
| 新增可选字段 | 1.0.0 → 1.1.0 | 否 (向后兼容) |
| 新增必需字段 | 1.0.0 → 2.0.0 | 是 |
| 修改字段语义 | 1.0.0 → 2.0.0 | 是 |
| 修改 task_spec 数值 (同结构) | 不变,但 freeze_hash 变 | 重跑实验 |

---

## 7. 联调检查清单 (M1 节点用)

朋友交付场景时,实验 agent 这边需要验证:

- [ ] 能用 `python -c "from scenarios.<task_id>.env import DroneRingEnv"` 导入
- [ ] 能 `env.reset(seed=0)` 不报错
- [ ] 能 `env.step({"red": np.zeros(4), "blue": np.zeros(4)})` 不报错
- [ ] `obs.shape` 与 `task_spec.observation_space.shape` 一致
- [ ] `info` 包含本文档 §3.2 列出的所有字段
- [ ] `evaluation_metrics.primary.name` 与 `evaluator/benchmark.py` 中实现一致
- [ ] `manifest.json` 中 `freeze_hash` 已写入

任何一项不通过 → 当场退回,不进入下一阶段。

---

## 附录 A:与第二份合同 (PolicyPackage) 的衔接点

策略设计 Agent 在生产 PolicyPackage 时,必须:

1. **读取本合同 §2.4 `action_space`** → 决定 `policy.act()` 的输出形状
2. **读取本合同 §2.3 `observation_space`** → 决定 `policy.act()` 的输入形状
3. **读取本合同 §2.5 `reward_structure`** → 设计训练目标
4. **遵守本合同 §2.6 `termination_conditions`** → 训练时正确处理 episode 边界
5. **写入 PolicyPackage 的 `algorithm_card.md` 中** → 标注"此策略针对 task_id=X 设计"

详见 `INTERFACE_2_POLICY_TO_AUTORESEARCH.md`。
