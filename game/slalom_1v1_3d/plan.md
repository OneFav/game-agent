# slalom_1v1_3d 实施计划

## 一、需求分析

- **任务族**：目标语义属于 `swarm_combat`，但共享合约 [src/contracts/scenario_schema.yaml] 仍只枚举 `drone_ring_game`。因此本次按 `game-init`/`game-main` 要求采用“**计划与总结明确说明 + 场景包内做 3D 适配层**”的方式落地，不修改共享 `src/contracts/hooks`。
- **场景描述摘要**：红蓝双方各 1 架赛车机，在 `slalom` 门布局中进行 3D 对抗，通信为完美通信，动力学为 `DoubleIntegrator3D`，超时 400 步。
- **形式化定义**：`formalism = MarkovGame`。双方同时决策、全局观测、无额外通信损失；红方目标是稳定穿越 `slalom` 门并累计团队得分，蓝方目标是阻截红方、争夺门得分并保持自身约束可行。
- **目标指标**：`swarm_combat · team_score >= 1.0`。本计划将 `team_score` 明确定义为**红方团队累计门得分的 episode 平均值**，并把 `gate_pass_reward` 固定为 `1.0`，使 README 中的阈值与环境积分同量纲。
- **关键参数表**：
  - `game_id = slalom_1v1_3d`
  - `task_id = slalom_1v1_3d_001`
  - `policy_id = slalom_1v1_3d_rule_v1`
  - `exp_id = slalom_1v1_3d_exp_001`
  - `teams = {red: 1 racer, blue: 1 racer}`
  - `gate_layout = slalom`
  - `gate_count = 5`，取自 `src/game_agent/envs/swarm_combat/config.py` 的 `build_gate_layout("slalom")`
  - `communication.mode = perfect`
  - `dynamics = DoubleIntegrator3D`
  - `max_steps = 400`
  - `primary_metric = team_score`
  - `hard_constraints = collision_rate <= 0.05, out_of_bounds_rate <= 0.01, action_violation_rate <= 0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `task_family` 继续写为 `drone_ring_game`，并在 `scenario_parameters.engine` 中显式声明真实执行引擎是 `swarm_combat`，这是对现有共享 schema 边界的受控适配。
  - `formalism` 采用 `MarkovGame`，因为此例不强调局部观测，也不存在防守机角色。
  - `observation_space` 采用固定长度 64 维 `Box`，包含：自身 3D 位置/速度、对手相对位置/速度、下一目标门的相对向量与法向、当前团队得分/过门数、边界裕度、完整门序列的相对几何与冷却信息。这样下游策略既可直接根据“下一目标门”导航，也能在需要时读取全门布局。
  - `action_space` 采用 3 维连续 `Box`，语义为 `[ax, ay, az]`，取值范围 `[-1, 1]`，再由场景内适配层映射到真实 `DoubleIntegrator3D` 的加速度上限。
  - `reward_structure` 只作为训练/分析信号：`gate_progress_reward`、`intercept_pressure_reward`、`collision_penalty`、`out_of_bounds_penalty`、`time_penalty`。其中不会出现与主指标同名的组件，避免 reward hacking。
  - `evaluation_metrics.primary.name = team_score`，方向 `maximize`。
  - `evaluation_metrics.secondary` 包含 `blue_team_score`、`red_win_rate`、`avg_episode_length`、`gate_pass_balance`。
  - `termination_conditions` 包含：任一方出界、任一碰撞触发双负、达到 `max_steps=400`；不提前设 `target_score`，避免为了刷分过早截断回合。
- **env.py 需求**：
  - 使用 `game_agent.envs.swarm_combat.EnvConfig` 与 `SwarmCombatEnv` 作为真实 3D 执行内核。
  - 在场景包内提供一个轻量包装器，完成 3 个适配动作：
    1. 将原生 `int` 型 drone id 映射成稳定字符串 agent id：`red_racer_0`、`blue_racer_0`。
    2. 将原生全局观测压缩/重排为冻结的 64 维场景合约观测。
    3. 将原生 `info` 聚合为 hook/实验容易消费的 `metrics` 字段，包括 `team_score`、`collision`、`out_of_bounds`、`gate_passed_count`、`action_clipped`。
  - 场景包测试至少覆盖：`reset(seed)` 确定性、观测/动作 shape、一次零动作 rollout 的返回结构稳定性。
- **assumptions.md 要点**：
  - 用户未指定出发点，采用对称固定出生点，确保红蓝公平。
  - 用户未指定门得分权重，固定 `gate_pass_reward = 1.0` 以对齐 README 阈值。
  - 用户未指定终局积分阈值，因此只使用超时/碰撞/出界终止。

## 三、策略包设计

- **推荐算法族**：规则策略。
- **选择理由**：当前任务目标是按 README 完成示例 4 的端到端闭环，且不能修改共享运行器；规则策略最符合 KISS/YAGNI，可以直接对冻结观测做确定性决策，并通过小规模 sweep 快速收敛到 `team_score >= 1.0`。
- **策略架构**：
  - 输入：64 维冻结观测；兼容 hook 的 12 维 dummy 观测。
  - 输出：3 维加速度动作，最终统一 `np.clip` 到场景动作边界。
  - 红方策略：基于下一目标门的相对向量做导航，并使用对手相对位置/速度做短时避碰。
  - 蓝方策略：优先预测红方未来位置做拦截，而不是纯竞速过门。
  - safety gate：动作裁剪、边界回推、近距离分离、异常回退零动作。
- **搜索空间建议**：
  - `priority_1`：`racer_gain`、`intercept_gain`、`avoidance_gain`
  - `priority_2`：`prediction_horizon`、`boundary_gain`、`brake_bias`
  - `do_not_tune`：动作维度、团队人数、门布局、超时步数、`gate_pass_reward`

## 四、实验方案设计

- **搜索空间大小**：先做 9 个 `priority_1` 组合，每个组合 3 个 seed，共 27 个 episode；必要时再做二轮局部细化。
- **推荐 trial 数量**：首轮 9，二轮最多再补 4。
- **seeds 数量**：每个 trial 3 个 seed，固定使用 `[100, 101, 102]`。
- **预算估计**：规则策略无训练成本，主要消耗在 rollout；1v1 3D 400 步场景本地 CPU 可以在分钟级完成。
- **晋级标准**：
  - 所有硬约束通过；
  - `team_score >= 1.0`；
  - 若多个 trial 都满足，则优先 `team_score` 更高，其次 `avg_episode_length` 更低。
  - 若首轮出现“已达标但达标后继续 rollout 引入额外碰撞”的模式，则允许把终止条件收紧为 `target_team_score = 1.0`，前提是该调整在 `summary.md` 中明确记录，并说明它是为对齐 README 示例 4 的验收阈值而做的场景适配，而不是修改共享 hook 或合同。

## 五、交接说明

- **Agent 1 → Agent 2**：
  - 场景包冻结 `action_space = 3D acceleration` 与 64 维观测结构；
  - 主指标是 `team_score`，不是 reward component；
  - 场景内 `engine = swarm_combat` 是关键适配点，策略不可假设 2D。
- **Agent 2 → Agent 3**：
  - `train.py` 必须保留标准 CLI；
  - `infer.py` 必须直接读取场景目录运行真实 3D rollout；
  - `search_space.yaml` 中所有参数必须出现在 `get_config_schema()`。
- **跨阶段约束**：
  - 不修改共享 `src/contracts/hooks`；
  - 场景包与策略包生成 manifest 后视为冻结输入；
  - 实验排名只能读 `evaluation_metrics` 与硬约束。

## 六、预期产出

- **`scenarios/slalom_1v1_3d_001/`**：
  - `task_spec.yaml`、`env_config.yaml`、`env.py`、`model.md`、`assumptions.md`、`tests/`、`manifest.json`
- **`policies/slalom_1v1_3d_rule_v1/`**：
  - `policy.py`、`train.py`、`infer.py`、`default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`requirements.txt`、`tests/`、`metadata.json`、`manifest.json`
- **`experiments/slalom_1v1_3d_exp_001/`**：
  - `trials/*`、`leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`
- **可视化**：
  - `output/example_04_slalom_1v1_3d.png`

## 七、风险与未知

- **系统边界风险**：共享 schema 尚未直接支持 `swarm_combat`，因此本次必须在 `plan.md/summary.md` 中写明：这是按三阶段接口产出的适配包，而不是修改共享协议后的原生任务族。
- **指标解释风险**：README 只写 `team_score >= 1.0`，未明确是红方原始 reward、净胜分还是累计过门数。本计划采用“红方团队累计门得分，且每次过门记 1 分”的显式定义，并在 summary 复述。
- **策略风险**：若蓝方拦截过强导致频繁碰撞，先调低 `intercept_gain`、增大 `avoidance_gain` 与 `prediction_horizon`。
- **可视化风险**：PNG 必须来自真实 3D 历史轨迹，禁止像旧 2D 示例那样只做伪 3D 投影。

## 八、验证清单

- [x] 已列出用户文本中可确定的全部关键参数
- [x] 已写明默认值及其理由
- [x] `task_id / policy_id / exp_id` 已按要求固定
- [x] 已明确说明 `swarm_combat` 与共享 schema 的边界适配
- [x] 本计划可直接作为 `game-main` 的执行输入
