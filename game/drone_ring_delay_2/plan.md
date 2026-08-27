# drone_ring_delay_2 实施计划

## 一、需求分析

- **任务族**：`drone_ring_game`
- **场景描述摘要**：红方无人机需要在 100 步内穿过两个圆环，蓝方负责追击拦截；双方决策受通信延迟 2 步影响。
- **形式化定义**：`formalism: POSG`。红方目标是在硬约束满足前提下最大化穿环成功率并缩短完成时间；蓝方目标是通过追击缩短红方与己方距离并提高拦截概率。通信延迟会削弱基于对方实时状态的反应能力，因此策略设计需要对短期预测和安全裕度更敏感。
- **关键参数表**：
  - `game_id`: `drone_ring_delay_2`
  - `task_id`: `drone_ring_delay_2_001`
  - `policy_id`: `drone_ring_delay_2_rule_v1`
  - `exp_id`: `drone_ring_delay_2_exp_001`
  - `ring_count`: 2
  - `max_steps`: 100
  - `communication.mode`: `delayed`
  - `communication.delay_steps`: 2
  - `primary_metric`: `success_rate`
  - `target_metric`: `success_rate >= 0.55`
  - `secondary_metrics`: `collision_rate`、`timeout_rate`、`avg_episode_length`
  - `hard_constraints`: `collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate <= 0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `task_family` 固定为 `drone_ring_game`，`formalism` 固定为 `POSG`。
  - `agents` 保持两方一机：`red_0` 为 runner，`blue_0` 为 interceptor。
  - `observation_space` 保持现有 12 维 Box，复用仓库基线环境接口，避免引入共享协议变更。
  - `action_space` 保持 4 维连续动作，与现有 `DroneRingEnv.action_shape == (4,)` 一致；策略只消费前两维平面运动分量，后两维保留兼容。
  - `reward_structure` 继续使用 `ring_progress`、`interception`、`timeout_penalty`，并与 `evaluation_metrics.primary.name = success_rate` 保持名称隔离，避免 reward hacking。
  - `evaluation_metrics` 继续以 `success_rate` 为主指标，`collision_rate`、`timeout_rate`、`episode_length` 为次指标，并声明三项硬约束。
  - `termination_conditions`：红方通过全部圆环、蓝方碰撞拦截、任一方出界、超时 100 步。
  - `splits`：保持轻量实验配置；实验阶段至少使用 3 个 seed 做交叉验证。
- **env.py 需求**：
  - 直接复用场景编译器输出的自包含 2D 环境模板，保持 reset/step 确定性和 hook 兼容。
  - `env_config.yaml` 显式落地 `ring_count=2`、`max_steps=100`、`ring_radius=0.45`、`collision_radius=0.25`、`boundary=10.0`。
  - 虽然共享 runner 当前不直接消费 `scenarios/<task_id>/env.py`，但场景包仍需完整提供它，确保 package 自描述且能通过 hook。
- **assumptions.md 要点**：
  - 未显式给出环半径、边界和碰撞半径，沿用基线保守默认值。
  - 未显式给出通信作用在哪个子系统，M1 阶段把“2 步延迟”落在策略侧的对手状态使用上，而不是修改共享环境动力学。
  - 未显式给出蓝方成功定义，沿用“红蓝接触即蓝方拦截成功”的现有环境语义。

## 三、策略包设计

- **推荐算法族**：规则策略
- **选择理由**：示例 2 仍是轻量 2D 几何博弈，且 README/现有实现都以规则策略 + 小规模 sweep 为主路径。为了满足 KISS 和 YAGNI，不引入学习型训练，只通过规则参数和延迟鲁棒性调优达成指标。
- **策略架构**：
  - 输入：12 维观测，红方侧读取目标环方向、敌我相对位移；蓝方侧读取相对速度与相对位移。
  - 输出：4 维动作，最终统一 `np.clip` 到 action bounds。
  - 红方逻辑：默认沿目标环方向推进；若与蓝方距离小于安全阈值则增加避障向量。
  - 蓝方逻辑：追击时对红方相对状态使用 2 步历史近似，模拟通信延迟下的滞后拦截；距离过近时优先减速，避免硬碰撞触发硬约束失败。
  - `safety_gate`：任何异常回退零动作，动作统一裁剪，近距离时优先规避。
- **搜索空间建议**：
  - `priority_1`：`speed_scale`、`intercept_gain`、`safety_margin`
  - `priority_2`：如首轮未达标，再扩展 `delay_compensation`、`pursuit_brake_distance`
  - `do_not_tune`：`policy_type`、动作维度、观测维度、通信延迟步数、环境终止条件

## 四、实验方案设计

- **搜索空间大小**：首轮沿用基线 18 组笛卡尔积，覆盖 `speed_scale(3) × intercept_gain(3) × safety_margin(2)`。
- **推荐 trial 数量**：18
- **seeds 数量**：3 个，优先 `[0, 1, 2]`
- **预算估计**：规则策略无需训练，18 个 trial × 3 个 seed × 最多 100 步，CPU 预算为分钟级。
- **晋级标准**：
  - 首要标准：`success_rate >= 0.55`
  - 同时必须满足所有 `hard_constraints`
  - 若多个 trial 同时满足，以 `avg_episode_length` 更短者优先
  - 若首轮不达标，则仅在 `policies/drone_ring_delay_2_rule_v1/search_space.yaml` 与 `default_config.yaml` 范围内迭代，不新增共享抽象

## 五、交接说明

- **Agent 1 → Agent 2**：
  - 场景包冻结后，策略端只能读取 `task_spec.yaml`、`env_config.yaml`、`manifest.json` 等信息，不得回写。
  - `evaluation_metrics` 才是实验排名依据；`reward_structure` 只做语义参考。
  - `communication.delay_steps = 2` 需要策略显式消费，不能假设共享环境已自动实现延迟。
- **Agent 2 → Agent 3**：
  - `PolicyClass` 必须兼容 `(config, env_spec)` 构造签名。
  - `search_space.yaml` 的参数名必须全部出现在 `get_config_schema()`。
  - `train.py` 和 `infer.py` 维持现有 CLI 合同，保证 AutoResearch 可直接调用。
- **跨阶段约束**：
  - 只允许写入 `game/drone_ring_delay_2/`、`scenarios/drone_ring_delay_2_001/`、`policies/drone_ring_delay_2_rule_v1/`、`experiments/drone_ring_delay_2_exp_001/`、`output/example_02_drone_ring_delay_2.png`
  - 禁止修改共享 `src/contracts/`、`src/hooks/`、`task.md`、其他示例目录
  - `manifest.json.freeze_hash` 视为冻结凭据，summary/log 必须记录

## 六、预期产出

- **`game/drone_ring_delay_2/`**：
  - `plan.md`：实施计划与参数抽取
  - `log.md`：按 `game-main` 阶段记录生成、验证、调参与结果
  - `summary.md`：最终汇总、指标与遗留说明
- **`scenarios/drone_ring_delay_2_001/`**：
  - `task_spec.yaml`、`env_config.yaml`、`env.py`、`model.md`、`assumptions.md`、`tests/`、`manifest.json`
- **`policies/drone_ring_delay_2_rule_v1/`**：
  - `policy.py`、`train.py`、`infer.py`、`default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`requirements.txt`、`tests/`、`metadata.json`、`manifest.json`
- **`experiments/drone_ring_delay_2_exp_001/`**：
  - `trials/`、`leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`
  - 如有需要，附带实验内可视化辅助脚本，但最终 PNG 必须输出到 `output/example_02_drone_ring_delay_2.png`

## 七、风险与未知

- 共享 `AutoResearchRunner` 当前直接实例化 `src/game_agent/envs/drone_ring_game/DroneRingEnv`，不会自动执行场景包内的 `env.py`。因此“通信延迟 2 步”的主实现位置需要放在策略逻辑和实验解释中，而不是依赖共享 runner 改造。
- 基线环境对两环任务较容易，首轮 sweep 很可能已经明显超过 `0.55`。若出现这种情况，仍需把 baseline 到 best trial 的参数搜索过程明确记录为“策略配置迭代”，避免 summary 只有结论没有过程。
- 若首轮成功率意外偏低，允许在策略目录内做最小范围改进，例如引入简易历史观测缓冲和更保守的蓝方追击速度，但不引入新训练框架。
- 若共享环境与包内 `env.py` 语义不完全一致，需要在 `summary.md` 明确记录 M1 的实现边界和结论范围。

## 八、验证清单

- [x] 用户描述中可确定的参数已列出
- [x] 默认值与策略侧延迟建模方式已说明
- [x] `task_id / policy_id / exp_id` 已固定为用户建议命名
- [x] 目录责任边界已锁定
- [x] 文档足够详细，可直接驱动后续 `game-main` 落地与迭代
