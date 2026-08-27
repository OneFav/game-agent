# wide_slalom_2v2 实施计划

## 一、需求分析

- **任务族**：`swarm_combat`
- **场景描述摘要**：红方 2 机（1 赛车机 + 1 防守机护航）对阵蓝方 2 机（1 赛车机 + 1 防守机拦截），采用 `wide_slalom` 3D 门布局，最长 600 步，目标是让红方编队在护航/拦截压力下稳定累计穿门得分。
- **形式化定义**：`formalism=POSG`。四机同时决策，红方防守机执行 escort，蓝方防守机执行 intercept；主指标按红方累计队伍得分 `team_score` 统计，蓝方累计得分与胜负结果作为 secondary 指标保留。
- **奖励耦合说明**：这是红蓝对抗博弈，红蓝奖励函数不得彼此独立。红方效用不仅来自己方赛车机穿越 `wide_slalom` 门序列，也必须受到真实蓝方拦截压力、敌方赛车机推进和跨队安全事件影响；蓝方效用必须反向依赖红方赛车机的推进受阻、蓝方赛车机穿门、蓝方防守机对红方赛车机的拦截距离。防守机的护航/拦截项都引用对方或己方 racer 的相对状态，避免退化为两个互不影响的单队任务。
- **关键参数表**：
  - `game_id=wide_slalom_2v2`
  - `task_id=wide_slalom_2v2_001`
  - `policy_id=wide_slalom_2v2_rule_v1`
  - `exp_id=wide_slalom_2v2_exp_001`
  - `n_red=2`, `n_blue=2`
  - `red_roles=[racer, defender(escort)]`
  - `blue_roles=[racer, defender(intercept)]`
  - `gate_layout=wide_slalom`, `gate_count=6`
  - `max_steps=600`
  - `communication.mode=perfect`
  - `primary_metric=team_score`
  - `target=team_score >= 2.0`
  - `hard_constraints=collision_rate<=0.05, out_of_bounds_rate<=0.01, action_violation_rate==0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `task_family=swarm_combat`，不再沿用旧版 `drone_ring_game` 兼容壳。
  - 观测使用共享 `SwarmCombatEnv` 的真实 3D 全局可观测向量，当前 2v2 + 6 gate 下为 `shape=[78]`。
  - 动作接口保留本地 4 维兼容层：前 3 维是归一化 XYZ 加速度，第 4 维保留，用于满足现有 Policy hook。
  - `reward_structure` 与 `evaluation_metrics` 分离，避免 reward hacking；主指标只使用 `team_score`。
  - 对抗耦合项必须显式写入 `reward_structure.components`：`red_gate_progress`、`blue_gate_progress`、`escort_protection`、`intercept_pressure`、`cross_team_safety_penalty`、`time_penalty`。其中 `escort_protection` 依赖己方 defender 到己方 racer 的距离以及敌方 defender 到己方 racer 的威胁距离；`intercept_pressure` 依赖防守机到敌方 racer 的距离和敌方 racer 当前门序进度。
  - 场景 wrapper 读取 `env_config.yaml`，将固定出生点、`wide_slalom` 门布局、奖励权重、目标步数注入共享 `SwarmCombatEnv`。
- **env.py 需求**：
  - 只做薄包装：命名 agent、归一化动作、把 `raw_env` 与全局比分信息放入 `info`，便于策略直接复用共享 3D 控制器。
  - 出生点采用对称固定位置 `(-20, ±8, 4.5)` / `(20, ±8, 4.5)`，确保 rollout 完全可复现。
  - 包内测试覆盖 reset 确定性、观测/动作 shape、四机 step 结构。
- **assumptions.md 要点**：
  - 以红方累计队伍得分作为主指标，蓝方得分作为 secondary。
  - 单次有效穿门计 1 分，使 `team_score >= 2.0` 与 README 示例量纲一致。
  - 不提前设置 `target_score=2.0` 截断，而是完整运行 600 步观察全程护航/拦截稳定性。

## 三、策略包设计

- **推荐算法族**：规则策略，底层复用共享 `SafeRulePolicy`，本地只做 team-aware 适配。
- **选择理由**：示例 5 的核心是 3D 几何轨迹、门前风险控制、护航/拦截角色分工，不需要引入大规模 RL；规则策略更符合 M1、KISS 和可复现实验要求。
- **策略架构**：
  - 主路径：从 `info["raw_env"]` 读取真实 `SwarmCombatEnv` 句柄，批量计算四机动作，再归一化回本地 4 维接口。
  - 红方 defender 维持 escort，蓝方 defender 改为 intercept，解决共享 `SafeRulePolicy` 单一 `defender_mode` 无法区分队伍的问题。
  - 回退路径：当 hook/test 不提供 `raw_env` 时，退回轻量 observation-only 几何规则，保证本地策略测试仍通过。
  - 安全机制：共享 lookahead collision check + boundary repulsion + gate-frame avoidance，再叠加本地动作归一化与 `np.clip`。
- **搜索空间建议**：
  - `priority_1`：`desired_speed`, `risk_margin`
  - `priority_2`：`position_gain`, `velocity_gain`, `boundary_margin`, `turn_steps`, `turn_lookahead`, `risk_lookahead_steps`, `brake_release_speed`, `lane_spacing`, `gate_approach_offset`, `gate_exit_offset`, `separation_gain`
  - `do_not_tune`：`reserved_action_value`

## 四、实验方案设计

- **搜索空间大小**：`desired_speed(3) x risk_margin(3) = 9` 个主 trial。
- **推荐 trial 数量**：9
- **seeds 数量**：3（`100,101,102`）
- **预算估计**：规则策略不训练，仅做 rollout；单次 9 x 3 x 600 步在本地 CPU 可控。
- **晋级标准**：
  - 所有硬约束通过
  - `team_score >= 2.0`
  - 空场测试通过：`Δ(coupling load)=U_R(红,∅)-U_R(红,真蓝)>0`，证明真实蓝方降低红方效用，博弈压力存在
  - 同分按 `avg_episode_length` 升序打破
  - 记录 pilot 校验与 full sweep 两轮过程

## 五、交接说明

- **Agent 1 → Agent 2**：
  - 场景冻结点在 `task_spec.yaml` 与 `env_config.yaml`；策略只读这些字段，不回写场景。
  - `info["raw_env"]` 是策略复用共享控制器的关键桥接点。
- **Agent 2 → Agent 3**：
  - `train.py` 保持无训练 no-op checkpoint 入口。
  - `infer.py` 负责真正计算 `team_score`、secondary metrics 和 hard constraints。
  - `search_space.yaml` 中所有字段必须出现在 `get_config_schema()`。
- **跨阶段约束**：
  - 不修改 `src/contracts/*`、`src/hooks/*`
  - 只在 `game/wide_slalom_2v2/`、`scenarios/wide_slalom_2v2_001/`、`policies/wide_slalom_2v2_rule_v1/`、`experiments/wide_slalom_2v2_exp_001/`、`output/example_05_wide_slalom_2v2.png` 内落地

## 六、预期产出

- **`scenarios/wide_slalom_2v2_001/`**：
  - `task_spec.yaml`, `env_config.yaml`, `env.py`, `assumptions.md`, `model.md`, `tests/`, `manifest.json`
- **`policies/wide_slalom_2v2_rule_v1/`**：
  - `policy.py`, `train.py`, `infer.py`, `default_config.yaml`, `search_space.yaml`, `algorithm_card.md`, `metadata.json`, `tests/`, `manifest.json`
- **`experiments/wide_slalom_2v2_exp_001/`**：
  - `trials/trial_0001..0009`, `leaderboard.csv`, `best_config.yaml`, `report.md`, `regression_report.md`, `visualize_best_trial.py`, `trajectory_3d_seed100.png`, `topdown_seed100.png`, `manifest.json`
  - `report.md` 必须记录空场测试的 `U_R(红,∅)`、`U_R(红,真蓝)` 和 `Δ(coupling load)`，且 `Δ > 0` 才能声明博弈存在
- **可视化**：
  - `output/example_05_wide_slalom_2v2.png`

## 七、风险与未知

- 当前主指标 `team_score` 采用红方累计得分口径；蓝方得分与 winner 用于辅助解释，但不参与主排序。
- `src/contracts/scenario_schema.yaml` 与部分 subagent TOML 仍把 `task_family` 写成仅支持 `drone_ring_game`，而本任务需要 `swarm_combat`；若验证仍沿用旧 schema，需要在场景包风险中明确该兼容缺口，或由后续实现补齐 schema/验证支持。
- 共享 `SafeRulePolicy` 原生只支持统一 defender mode，需要本地 team-aware 适配；若适配错误，会出现“双方 defender 都 escort / 都 intercept”的角色错配。
- 若奖励耦合项实现不生效，可能出现 `Δ(coupling load)<=0`，即真实蓝方没有降低红方效用；此时不得宣称对抗博弈成立，需要回到场景奖励或蓝方策略修正。
- 出生点过近会显著抬高 gate collision 风险，因此需要记录从紧凑编队到默认对称出生点的迭代修正。
- 由于不修改共享 runner，本地实验包需要显式用 `train.py + infer.py` 重新生成 `team_score` leaderboard。
