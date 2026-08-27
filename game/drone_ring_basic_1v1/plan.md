# drone_ring_basic_1v1 实施计划

## 一、需求分析

- **任务族**：`drone_ring_game`
- **场景描述摘要**：红方无人机需要按顺序穿过两个圆环，蓝方无人机追击并尝试拦截；双方通信为完美通信，episode 超时为 60 步。
- **形式化定义**：`formalism: POSG`。红方目标是在 60 步内完成双环穿越并避免碰撞或出界；蓝方目标是在同样约束下提升拦截概率、压低红方成功率。实验排名只看 `evaluation_metrics`，不使用 reward component 排名。
- **关键参数表**：
  - `game_id`: `drone_ring_basic_1v1`
  - `task_id`: `drone_ring_basic_1v1_001`
  - `policy_id`: `drone_ring_basic_1v1_rule_v1`
  - `exp_id`: `drone_ring_basic_1v1_exp_001`
  - `task_family`: `drone_ring_game`
  - `ring_count`: 2
  - `max_steps`: 60
  - `communication.mode`: `perfect`
  - `formalism`: `POSG`
  - `agents`: `red_0` runner，`blue_0` interceptor
  - `primary_metric`: `success_rate`
  - `target_metric`: `success_rate >= 0.7`
  - `hard_constraints`: `collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate <= 0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - 维持当前系统兼容的 `schema_version: "1.0"`、`task_family: drone_ring_game`、`formalism: POSG`。
  - `observation_space` 继续采用 12 维定长 Box，兼容现有 `DroneRingEnv` 和规则策略模板：
    - 自身位置 2 维
    - 自身速度 2 维
    - 对手相对位置 2 维
    - 对手相对速度 2 维
    - 剩余环比例 1 维
    - 当前目标环方向 2 维
    - 当前目标环距离 1 维
  - `action_space` 使用单 agent 4 维连续动作，前两维为平面加速度，后两维保留兼容占位。
  - `reward_structure` 只描述训练信号：`ring_progress`、`interception`、`timeout_penalty`，避免与主指标 `success_rate` 重名。
  - `evaluation_metrics.primary` 固定为 `success_rate`，secondary 关注 `collision_rate`、`timeout_rate`、`episode_length`，hard constraints 固定碰撞、出界和动作越界。
  - `termination_conditions`：红方完成全部圆环、蓝方完成拦截、任意出界、超时。
  - `splits` 采用轻量评估设置，实验阶段至少使用 3 个 seed 做 sweep。
- **env.py 需求**：
  - 复用项目现有 2D `DroneRingEnv` 行为模型，保证 reset/step 确定性。
  - 环数显式设为 2，步数显式设为 60，通信记录为 perfect。
  - 保持 observation `(12,)`、action `(4,)`，确保 hook 与策略模板直接兼容。
  - 包内测试至少覆盖 reset 确定性和 obs/action 形状。
- **assumptions.md 要点**：
  - 用户已明确给出双环、完美通信、60 步，不再把这些字段记为默认值。
  - 对未给出的几何参数采用当前参考环境默认值：`ring_radius=0.45`、`collision_radius=0.25`、`boundary=10.0`。
  - 评估 seeds 采用 `[0, 1, 2]`，因为当前 AutoResearch 轻量 runner 以多 seed 一致性为主。

## 三、策略包设计

- **推荐算法族**：规则策略
- **选择理由**：示例 1 是确定性 2D 几何博弈，现有 M1 主链路已提供规则策略模板与确定性 sweep。规则策略满足 KISS/YAGNI，足以在不扩展共享代码的前提下完成闭环验证。
- **策略架构**：
  - 输入：场景包冻结的 12 维观测和 `agent_id`。
  - 输出：4 维动作，最终统一 `np.clip(action, low, high)`。
  - 红方：沿当前目标环方向推进，并在蓝方过近时基于 `safety_margin` 做侧向避让。
  - 蓝方：利用相对速度/相对位置做追击，调节 `intercept_gain` 平衡追击强度与碰撞风险。
  - safety gate：异常时回退零动作，任何输出都做 bounds 裁剪。
- **搜索空间建议**：
  - `priority_1`：`speed_scale`、`intercept_gain`
  - `priority_2`：`safety_margin`
  - `do_not_tune`：`policy_type`、动作空间上下界、环境终止条件

## 四、实验方案设计

- **搜索空间大小**：3 (`speed_scale`) × 3 (`intercept_gain`) × 2 (`safety_margin`) = 18 个 trial
- **推荐 trial 数量**：18
- **seeds 数量**：每个 trial 3 个 seed
- **预算估计**：单个 episode 最多 60 步，18 × 3 共 54 个 rollout，本地 CPU 预计分钟级完成。
- **晋级标准**：
  - 首先满足全部 hard constraints
  - `success_rate >= 0.7`
  - 同分时优先 `avg_episode_length` 更短的配置
  - 若默认配置已满足指标，仍完成完整 sweep，输出 best config 和前 3 名

## 五、交接说明

- **Agent 1 → Agent 2**：
  - `task_spec.yaml` 中的 `observation_space`、`action_space`、`env_config`、`evaluation_metrics` 进入冻结态，策略阶段只读消费。
  - `reward_structure` 只用于训练语义，不作为实验排名依据。
- **Agent 2 → Agent 3**：
  - `policy.py` 必须导出 `PolicyClass` 并实现 `contracts.policy_protocol.Policy`。
  - `search_space.yaml` 中的所有可调字段必须出现在 `get_config_schema()`。
  - `train.py` / `infer.py` 保持现有接口签名，实验阶段只改配置，不改策略源码。
- **跨阶段约束**：
  - 仅允许写入 `game/drone_ring_basic_1v1/`、`scenarios/drone_ring_basic_1v1_001/`、`policies/drone_ring_basic_1v1_rule_v1/`、`experiments/drone_ring_basic_1v1_exp_001/`、`output/example_01_drone_ring_basic_1v1.png`
  - 不修改 `src/contracts/hooks`、`task.md`、其他示例目录
  - 每个包都要重建 `manifest.json.freeze_hash`

## 六、预期产出

- **`scenarios/drone_ring_basic_1v1_001/`**：
  - `task_spec.yaml`、`env_config.yaml`、`env.py`、`model.md`、`assumptions.md`、`tests/`、`manifest.json`
  - 核心内容是双环、perfect communication、60 步上限的 1v1 场景定义
- **`policies/drone_ring_basic_1v1_rule_v1/`**：
  - `policy.py`、`train.py`、`infer.py`、`default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`requirements.txt`、`tests/`、`metadata.json`、`manifest.json`
  - 核心内容是规则追环/追击策略及 18 trial 搜索空间
- **`experiments/drone_ring_basic_1v1_exp_001/`**：
  - `trials/`、`leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`
  - 核心内容是 sweep 结果、top 配置和成功率证明
- **`output/example_01_drone_ring_basic_1v1.png`**：
  - 2D 轨迹图，展示双环位置、红蓝轨迹与 best trial 的一次代表性 rollout

## 七、风险与未知

- **需要进一步明确的问题**：
  - 完美通信在当前 1v1 参考环境中不直接影响动力学，只作为场景语义和日志字段保留。
  - 当前 runner 以固定 seed rollout 评估，不做真实训练；若用户期望学习型策略，需要扩展范围，但本任务不扩。
- **当前系统不支持的功能**：
  - 不扩展到新的任务族或高保真无人机仿真。
  - 不增加共享的可视化工具脚本，2D PNG 仅为当前示例独立产出。
- **预期失败模式和应对策略**：
  - 若 `intercept_gain` 过高，蓝方可能导致碰撞率上升：通过 sweep 选择更温和的拦截增益。
  - 若 `speed_scale` 过低，红方可能在 60 步内超时：通过提升速度比例和降低安全边距平衡成功率。
  - 若默认 assumptions 文案与用户显式描述不一致，编译后立即在目标场景目录内修正并重建 manifest。

## 八、验证清单

- [x] 用户可确定参数已全部列出：2 环、perfect communication、60 步、1v1、目标成功率 0.7
- [x] 默认值与理由已列出：几何半径、边界、评估 seeds
- [x] `task_id` / `policy_id` / `exp_id` 已使用用户建议命名
- [x] 未引入新任务族
- [x] 文档长度满足后续 `game-main` 执行和迭代需要
