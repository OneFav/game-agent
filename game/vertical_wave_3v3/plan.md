# vertical_wave_3v3 实施计划

## 一、需求分析

- **任务族**：计划语义为 `swarm_combat`，但当前 `contracts/scenario_schema.yaml` 仍只允许 `task_family: drone_ring_game`。因此落地时采用“合同兼容壳 + `swarm_combat` 执行引擎”：`task_family=drone_ring_game` 保证 hook 通过，`scenario_parameters.engine` / `env_config.engine` 记录真实 3D 多机对抗语义。
- **场景描述摘要**：红方 3 机（2 赛车机 + 1 防守机）对阵蓝方 3 机（2 赛车机 + 1 防守机），使用 `vertical_wave` 布局、随机出生、超时 600 步。核心需求是双赛车机多车道分配、防守机护航/拦截，以及前视碰撞检测。
- **形式化定义**：`formalism=POSG`。红蓝双方同时决策，单机局部观测由固定长度向量承载；评估器可在策略包内部通过适配器访问完整环境状态以生成 6 机动作。
- **奖励耦合说明**：这是对抗博弈，红蓝奖励不得彼此独立。红方效用依赖己方赛车机穿门、蓝方拦截压力、队内/队间安全事件；蓝方效用依赖蓝方赛车机推进、对红方赛车机的拦截压力、红方被迫减速或偏航，以及同样的碰撞/出界惩罚。防守机奖励必须引用己方 racer 与对方 racer 的相对状态，避免退化为两个互不影响的单队任务。
- **指标职责说明**：场景包只提供中性观测指标和硬约束，如 `red_score`、`blue_score`、`score_margin`、`collision_rate`、`out_of_bounds_rate`、`action_violation_rate`、`avg_episode_length`。红/蓝某一方是否达标由策略包在 `mode=initial|red|blue` 的 `optimization_target` 中定义，默认优势阈值为 `0.0`。
- **关键参数表**：
  - `game_id=vertical_wave_3v3`
  - `task_id=vertical_wave_3v3_001`
  - `policy_id=vertical_wave_3v3_rule_v1`
  - `exp_id=vertical_wave_3v3_exp_001`
  - `gate_layout=vertical_wave`
  - `n_red=3`，`n_red_racers=2`，`n_red_defenders=1`
  - `n_blue=3`，`n_blue_racers=2`，`n_blue_defenders=1`
  - `spawn_mode=random`
  - `max_steps=600`
  - `communication.mode=perfect`
  - `dynamics=double_integrator`
  - `required_features=multi_lane_assignment, lookahead_collision_check`
  - `hard_constraints=collision_rate<=0.05, out_of_bounds_rate<=0.01, action_violation_rate==0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `schema_version: "1.0"`，`task_family: drone_ring_game`，`formalism: POSG`。
  - `agents` 显式声明 6 个 agent：`red_racer_0`、`red_racer_1`、`red_defender_0`、`blue_racer_0`、`blue_racer_1`、`blue_defender_0`。
  - `observation_space` 使用固定长度 Box，按当前 3v3 `swarm_combat` 适配器维持 `shape: [94]`，包含自身状态、门序列局部信息、队友/对手相对状态和角色编码。
  - `action_space` 为单机 3D 加速度，`shape: [3]`，`low/high` 对齐 `max_accel=10.0`，策略和环境均需 clip 并在 info 中记录 `action_clipped`。
  - `reward_structure.components` 包含耦合项：`red_gate_progress`、`blue_gate_progress`、`lane_assignment_bonus`、`escort_protection`、`intercept_pressure`、`cross_team_safety_penalty`、`collision_penalty`、`boundary_penalty`、`time_penalty`。
  - `evaluation_metrics` 保持中性：primary 可用 `red_score` 或 `score_margin` 作为可观测排序项，但不得写死“红方成功阈值”；secondary 包含 `blue_score`、`avg_episode_length`、`lane_conflict_count`、`near_miss_count`；hard constraints 包含碰撞、出界、动作越界。
  - `termination_conditions`：`max_steps=600`、目标分数达成、碰撞结束、出界结束。
- **env.py 需求**：
  - 复用 `src/game_agent/envs/swarm_combat`，场景包内只写薄包装，不复制共享源码。
  - `env_config.yaml` 必须把旧产物中的 `max_steps: 800` 更新为 `600`。
  - 随机出生必须由 `reset(seed)` 控制，保留最小出生间距，避免初始队内碰撞。
  - 多车道分配需要在门的局部切向/法向坐标中给两个 racer 分配不同 lateral offset。
  - 前视碰撞检测需要对未来 `risk_lookahead_steps` 做位置外推，检查队内、队间、门框和边界风险。
  - 包内测试至少覆盖 reset 确定性、观测/动作 shape、随机出生最小间距、600 步超时配置。
- **assumptions.md 要点**：
  - 未指定通信异常，默认 `perfect`。
  - 未指定门数，沿用 `vertical_wave` 模板默认门序列。
  - 未指定动力学，默认 `double_integrator`，因当前规则策略和参考环境已覆盖。
  - 未指定防守机模式，红方防守机默认护航己方最近 racer，蓝方防守机默认拦截对方领先 racer。

## 三、策略包设计

- **推荐算法族**：规则策略，基于 `SafeRulePolicy` / `SafeRulePolicyAdapter` 的 3D 多机安全规则扩展。
- **策略选择模式**：必须支持 `initial` / `red` / `blue`。`initial` 建立 RedPolicy/BluePolicy 基线；`red` 只优化红方策略和红方参数；`blue` 只优化蓝方策略和蓝方参数。
- **成功指标定义**：策略包写入 `optimization_target`。建议 `utility_definition.red_utility=avg_red_score`，`utility_definition.blue_utility=avg_blue_score`；红方轮使用 `red_utility - blue_utility > 0`，蓝方轮使用 `blue_utility - red_utility > 0`。
- **选择理由**：当前需求是几何路径、多机避碰和角色分工，规则策略可直接表达车道分配和前视风险检查，避免引入大规模 RL 训练，符合 KISS/YAGNI。
- **策略架构**：
  - `policy.py` 导出 `PolicyClass`，内部显式包含 `RedPolicy` 与 `BluePolicy` 或 `red_policy.py` / `blue_policy.py`。
  - `PolicyClass.act()` 只负责 team/role 分派、异常回退和 action bounds 裁剪。
  - RedPolicy：双 racer 根据门局部坐标分配 `red_lane_offsets`，defender 护航领先或受威胁 racer。
  - BluePolicy：双 racer 同样穿门争分，defender 拦截红方领先 racer 或威胁更高的 racer。
  - `safety_gate`：前视碰撞检测、队内间距、队间安全半径、门框避让、边界回推、紧急刹车。
- **搜索空间建议**：
  - `priority_1`：`red_desired_speed`、`blue_desired_speed`、`red_lane_spacing`、`blue_lane_spacing`、`red_risk_margin`、`blue_intercept_gain`
  - `priority_2`：`shared_turn_lookahead`、`shared_risk_lookahead_steps`、`red_escort_gain`、`blue_intercept_radius`、`shared_gate_approach_offset`
  - `do_not_tune`：agent 数量、角色数量、`gate_layout`、`spawn_mode`、`max_steps`、动作边界、硬约束阈值

## 四、实验方案设计

- **搜索空间大小**：先控制在 12~18 个 trial，优先扫 `priority_1`，避免 6 机随机出生下组合爆炸。
- **推荐 trial 数量**：首轮 18；若进入 `$game-main --rounds X`，后续每个红/蓝 best-response 轮建议 8~12 个 trial。
- **seeds 数量**：每个 trial 至少 3 个 seed，必须覆盖随机出生差异。
- **预算估计**：规则策略无训练成本，主要耗时来自 6 机 600 步 rollout、3 seed 和 2D/3D 可视化；预计单轮 sweep 可在轻量本地预算内完成。
- **晋级标准**：
  - 所有 hard constraints 通过；
  - 当前 `target_side` 的优势指标大于 `0.0`；
  - 空场耦合测试通过：红方轮 `Δ_R=U_R(红,∅蓝)-U_R(红,真蓝)>0`，蓝方轮 `Δ_B=U_B(蓝,∅红)-U_B(蓝,真红)>0`；
  - 跨 seed 稳定性满足报告中声明的容差。

## 五、交接说明

- **Agent 1 -> Agent 2**：
  - 场景包必须明确 `engine=swarm_combat`、`layout=vertical_wave`、`max_steps=600`、随机出生和 6 agent 角色。
  - `reward_structure` 是训练信号，必须含红蓝耦合项；`evaluation_metrics` 是中性观测指标，不负责定义红/蓝成功阈值。
  - 观测维度、动作维度、动作边界一旦冻结，下游不得隐式改变。
- **Agent 2 -> Agent 3**：
  - 策略包必须显式区分 RedPolicy/BluePolicy，并写明 `optimization_target.utility_definition`。
  - `default_config.yaml`、`search_space.yaml`、`get_config_schema()` 中红蓝参数必须加 `red_` / `blue_` 前缀；共享参数必须加 `shared_` 前缀并在 `algorithm_card.md` 说明理由。
  - `train.py` / `infer.py` CLI 签名保持合同兼容，`infer.py` 输出 `red_score`、`blue_score`、`advantage_score`、hard constraints 和 per-seed 结果。
- **跨阶段约束**：
  - 不修改 `src/`、`contracts/`、`hooks/`。
  - 场景包冻结后策略只读消费；实验阶段默认只调参，必要时才进入受控策略代码迭代。
  - 如果已有 `scenarios/vertical_wave_3v3_001` 仍是 `max_steps=800`，必须视为与本计划不一致并重生成或修正到 600。

## 六、预期产出

- **`scenarios/vertical_wave_3v3_001/`**：`task_spec.yaml`、`env_config.yaml`、`env.py`、`model.md`、`assumptions.md`、tests、`manifest.json`；关键配置为 `vertical_wave`、随机出生、6 agent、`max_steps=600`。
- **`policies/vertical_wave_3v3_rule_v1/`**：红蓝显式分离规则策略、默认配置、搜索空间、算法卡、CLI 入口、包内测试和 manifest。
- **`experiments/vertical_wave_3v3_exp_001/`**：deterministic sweep、leaderboard、best config、report、空场耦合测试 JSON、可视化脚本。
- **可视化**：`experiments/vertical_wave_3v3_exp_001/trajectory_3d_seed*.png`、`topdown_seed*.png`，以及 `output/example_06_vertical_wave_3v3.png`。

## 七、风险与未知

- **需要进一步明确的问题**：用户未指定门数、场地尺寸、随机出生范围、红蓝 racer 是否双向穿门；本计划采用当前 `vertical_wave` 模板默认值和 `team_forward` 方向。
- **当前系统不支持的功能**：合同层 `task_family` 仍只允许 `drone_ring_game`，`ScenarioCompiler` 与 `AutoResearchRunner` 的主实现偏 1v1/2D，因此 3v3 需要适配包和策略包内 evaluator 来承接 `swarm_combat`。
- **既有产物不一致风险**：当前已有 `vertical_wave_3v3` 产物可能基于 800 步；本次需求为 600 步，后续执行必须更新 freeze_hash，不能复用旧场景 manifest 当作完成。
- **预期失败模式**：
  - 随机出生过近导致起步碰撞；
  - 两个 racer lane offset 太小导致门前拥堵或队内碰撞；
  - `turn_lookahead` 过大导致 vertical wave 高度变化处切弯撞门框；
  - 防守机拦截路径穿越己方 racer 车道。
- **应对策略**：
  - 先用保守速度、大车道间距和较高风险半径建立 safe baseline；
  - 再分别对红/蓝侧做 best-response 调参；
  - 每轮都保留 hard constraints、空场耦合测试、`best_response_gain_side` 和 per-seed 失败样本。
