# figure_eight_4v4 实施计划

## 一、需求分析

- **任务族**：共享合同层仍写作 `drone_ring_game`，但语义任务族是 `swarm_combat`。这不是偷换概念，而是当前 `src/contracts/scenario_schema.yaml` 只允许 `drone_ring_game`，README 示例 4-7 已经通过“合同兼容壳 + 真实 3D 内核”方式适配更复杂场景。
- **场景描述摘要**：红方 4 机（2 赛车机、2 防守机）对阵蓝方 4 机（2 赛车机、2 防守机），使用 `figure_eight` 3D 门布局，双方按照 `team_forward` 规则从相反方向穿门，动力学模型为 `DampedDoubleIntegrator3D`，超时 1200 步，并要求做全参数空间 sweep 和 3D 可视化。
- **形式化定义**：`formalism: POSG`。双方同时决策，单机观测是固定长度局部向量，下游策略阶段允许通过同一三阶段接口下的适配包装器访问完整 `SwarmCombatEnv` 以进行批量动作计算。红方目标函数是最大化规范化 `team_score`，蓝方目标是竞争通过率并压低红方得分，同时双方都要满足碰撞率、出界率、动作违规率等硬约束。
- **命名约定**：
  - `game_id`: `figure_eight_4v4`
  - `task_id`: `figure_eight_4v4_001`
  - `policy_id`: `figure_eight_4v4_rule_v1`
  - `exp_id`: `figure_eight_4v4_exp_001`
- **关键参数表**：
  - `layout`: `figure_eight`
  - `n_red = 4`，`n_blue = 4`
  - `n_red_racers = 2`，`n_blue_racers = 2`
  - `red_defenders = 2`，`blue_defenders = 2`
  - `dynamics`: `DampedDoubleIntegrator3D`
  - `communication.mode`: `perfect`
  - `max_steps`: `1200`
  - `primary_metric`: `team_score`
  - `metric_target`: `team_score >= 4.0`
  - `visualization`: `output/example_07_figure_eight_4v4.png`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `task_family` 保持 `drone_ring_game` 仅用于通过共享 hook；真实语义写入 `scenario_parameters.semantic_task_family = swarm_combat`。
  - `observation_space` 使用 110 维：`6 + 7*8 + 6*8`，正好对应 8 机、6 门的 `SwarmCombatEnv` 原生观测结构。
  - `action_space` 采用 3 维连续动作 `[ax, ay, az]`，直接映射到 3D 加速度命令，避免再套一层 4 维兼容壳。
  - `reward_structure` 只保留 shaping 解释；主指标严格用 `team_score`，避免 reward hacking。
  - `evaluation_metrics.primary.name = team_score`，并固定 `gate_pass_reward = 1.0`，让 `team_score` 直接等于红方有效穿门数。
  - `hard_constraints` 设为 `collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate <= 0.0`。
  - `termination_conditions` 保留碰撞、出界、超时；不额外设置较低 target score，避免人为提前截断掩盖后半程稳定性。
- **env.py 需求**：
  - 使用 `SwarmCombatEnv` 作为真实执行内核。
  - 提供合同兼容 wrapper：字符串 agent id、`base_env` 访问、固定长度 info 字段。
  - `reset(seed)` 必须确定性；因此固定出生点，不把随机出生混入 sweep。
  - 场景测试至少覆盖 reset 确定性与 obs/action 形状。
- **assumptions.md 要点**：
  - 解释为什么 `task_family` 仍为 `drone_ring_game`。
  - 解释 `team_score` 与 `gate_pass_reward = 1.0` 的量纲对齐。
  - 解释为何使用固定出生点和 110 维原生观测。

## 三、策略包设计

- **推荐算法族**：规则策略。
- **选择理由**：当前约束是不改共享 runner/hook，只在限定目录内完成端到端闭环。规则策略最符合 KISS/YAGNI，可直接复用 `SafeRulePolicy` 的碰撞前瞻、边界避让和多 racer 分道逻辑，并通过有限 sweep 快速收敛。
- **策略架构**：
  - `PolicyClass` 继承共享 `Policy` ABC。
  - `act()` 作为合同兼容 fallback，只做单步局部观测裁剪输出。
  - `compute_actions(env)` 作为主路径，直接调用 `SafeRulePolicy.compute_actions(base_env)`。
  - 动作统一执行 `np.clip`，保证 `action_violation_rate = 0.0`。
- **搜索空间建议**：
  - `priority_1`：`desired_speed`、`lane_spacing`、`turn_lookahead`
  - `priority_2`：`risk_margin`、`defender_mode`
  - `do_not_tune`：`position_gain`、`velocity_gain`、`boundary_margin`、`turn_steps`、`risk_lookahead_steps`、`brake_release_speed`、`gate_approach_offset`、`gate_exit_offset`、`separation_gain`

## 四、实验方案设计

- **搜索空间大小**：`3 x 2 x 2 x 1 x 1 = 12` 个 trial。因为 `risk_margin` 与 `defender_mode` 在本轮冻结为单值，所以这已经是当前搜索空间的全量笛卡尔积。
- **推荐 trial 数量**：12，全部执行，不做抽样。
- **seeds 数量**：3 个，使用 `100, 101, 102`。
- **预算估计**：单个 3-seed trial 大约 20-25 秒，12 个 trial 约 4-5 分钟，能在当前仓库环境内接受。
- **晋级标准**：
  1. 所有 hard constraints 通过；
  2. `team_score >= 4.0`；
  3. `team_score` 跨 seed 标准差尽量为 0；
  4. 若主指标并列，则 `avg_episode_length` 更短者优先。

## 五、交接说明

- **Agent 1 → Agent 2**：
  - `task_spec.yaml` 的主指标是 `team_score`，不是奖励分。
  - 真实动作空间是 3 维加速度，不允许策略再假设 4 维 velocity setpoint。
  - 场景 wrapper 暴露 `base_env`，策略可安全使用全环境几何信息。
- **Agent 2 → Agent 3**：
  - `train.py` 只是生成 checkpoint，不做 RL 训练。
  - `infer.py` 必须输出 `team_score / blue_team_score / score_margin / red_win_rate / hard_constraints`。
  - 全空间 sweep 只允许修改 `search_space.yaml` 中声明的字段。
- **跨阶段约束**：
  - 不改 `src/contracts`、`src/hooks`、`task.md`。
  - 场景和策略冻结后，实验阶段只能改配置，不能改代码。

## 六、预期产出

- **`scenarios/figure_eight_4v4_001/`**：
  - `task_spec.yaml`：8 机 3D figure-eight 合同兼容定义。
  - `env_config.yaml`：固定出生点、damped dynamics、1200 步等真实执行参数。
  - `env.py`：`SwarmCombatEnv` wrapper。
  - `assumptions.md`、`model.md`、`tests/`、`manifest.json`。
- **`policies/figure_eight_4v4_rule_v1/`**：
  - `policy.py`：基于 `SafeRulePolicy` 的规则控制器包装。
  - `train.py` / `infer.py`：合同化训练与评估入口。
  - `default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`tests/`、`metadata.json`、`manifest.json`。
- **`experiments/figure_eight_4v4_exp_001/`**：
  - `trials/`：12 个 trial 的 config / metrics / log。
  - `leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`。
  - `visualize_best_trial.py` 或等价可复现脚本，用于输出 `output/example_07_figure_eight_4v4.png`。

## 七、风险与未知

- **共享场景 schema 边界**：`src/contracts/scenario_schema.yaml` 仍只枚举 `drone_ring_game`。必须在 plan/summary 中明确，本次由同一三阶段接口下的适配包承载 `swarm_combat` 语义。
- **共享实验 runner 边界**：`src/game_agent/autoresearch/runner.py` 固定使用 `DroneRingEnv`，不能直接运行 4v4 3D。因此实验阶段需要在 `experiments/figure_eight_4v4_exp_001/` 内按同接口产出自适配 ExperimentPackage。
- **策略表达力边界**：`SafeRulePolicy` 的 defender mode 仍是全局单值，本轮先优先完成可行稳定的红方 `team_score` 目标；若不足再考虑在策略包内局部扩展，而不是动共享代码。
- **失败模式**：
  - `desired_speed` 过高会在 figure-eight 中心交叉区碰撞。
  - `lane_spacing` 过小会让双 racer 在同门前拥堵，导致 `team_score` 卡在 3。
  - `turn_lookahead` 过大或过小都会降低重新对准下一个门的效率。

## 验证清单

- [x] 用户描述可确定的参数已列出：4v4、角色、`figure_eight`、`DampedDoubleIntegrator3D`、1200 步、全参数 sweep、3D 可视化。
- [x] 默认值均在 assumptions 章节有理由。
- [x] `task_id / policy_id / exp_id` 已固定为用户建议命名。
- [x] 已明确标注 `swarm_combat` 与共享合同/runner 的能力边界，并要求用同一三阶段接口产出适配包。
- [x] 本计划超过 500 字，可直接作为 `game-main` 的执行输入。
