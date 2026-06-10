# wide_slalom_2v2 实施计划

## 一、需求分析

- **任务族**：`drone_ring_game` 的复杂变体。语义仍是红方穿越门/环、蓝方拦截，但 2v2 编队、赛车机/防守机角色和 `wide_slalom` 布局超过当前 `drone_ring_game` 1v1 参考环境能力，建议用现有 `swarm_combat` 参考模块作为环境实现底座，同时保持 `task_family: drone_ring_game` 以符合当前 schema。
- **场景描述摘要**：红方 2 架无人机由 1 架赛车机执行穿门竞速、1 架防守机护航；蓝方 2 架无人机由 1 架赛车机竞争穿门、1 架防守机拦截；场景使用 `wide_slalom` 门布局，最大 episode 长度 600 步。
- **形式化定义**：`formalism: POSG`。双方同时决策，存在对抗、护航、拦截和局部观测；红方目标是让赛车机稳定穿越 `wide_slalom` 门序列并降低被拦截/碰撞概率，蓝方目标是最大化拦截和阻断，同时保持自身约束可行。
- **关键参数表**：
  - `game_id`: `wide_slalom_2v2`
  - `task_id`: `wide_slalom_2v2_001`
  - `policy_id`: `wide_slalom_2v2_rule_v1`
  - `exp_id`: `wide_slalom_2v2_exp_001`
  - `red_count`: 2
  - `red_roles`: 1 `racer` + 1 `defender`，防守机模式 `escort`
  - `blue_count`: 2
  - `blue_roles`: 1 `racer` + 1 `defender`，防守机模式 `intercept`
  - `gate_layout`: `wide_slalom`
  - `gate_count`: 6，依据 `src/game_agent/envs/swarm_combat/config.py` 中 `build_gate_layout("wide_slalom")` 的现有配置
  - `max_steps`: 600
  - `communication.mode`: `perfect`，用户未给延迟或丢包，按保守默认值处理
  - `dynamics`: `double_integrator` for racer，`damped_double_integrator` for defender，复用 `swarm_combat.EnvConfig` 默认机型
  - `primary_metric`: `success_rate` 或 `team_score` 二选一；若保持 `drone_ring_game` 兼容，优先 `success_rate`
  - `hard_constraints`: `collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate == 0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - `schema_version: "1.0"`，`task_family: drone_ring_game`，`formalism: POSG`。
  - `agents` 建议显式列出 4 个 agent：`red_racer_0`、`red_defender_0`、`blue_racer_0`、`blue_defender_0`，每个 agent 写入 `team`、`role`、`behavior_mode`。
  - `observation_space` 需要从当前 1v1 `[12]` 扩展为固定长度 Box。建议每机观测包含自身状态、己方队友相对状态、两个敌方相对状态、下一门相对向量、剩余门比例和角色 one-hot；维度建议 `[32]` 或由场景编译阶段根据 `swarm_combat` wrapper 实际返回固定。
  - `action_space` 建议采用 3D 加速度或速度设定：`shape: [3]`，`semantics: acceleration_setpoint` 或 `velocity_setpoint`，边界对齐 `swarm_combat` 的 `max_accel/max_speed`。若必须保持当前策略模板兼容，可降级为 `[4]` 速度设定，但不推荐，因为 `wide_slalom` 是 3D 门布局。
  - `reward_structure` 用于训练信号，包含 `gate_pass`、`formation_tight`、`interception`、`protection`、`safety_violation`、`collision`、`out_of_bounds`、`time_penalty`。不要让 reward component 名称与 primary metric 同名。
  - `evaluation_metrics.primary` 建议 `success_rate`：红方赛车机按顺序穿越所有门且未违反硬约束的 episode 比例。若后续需要真正双边竞速排名，可新增 `team_score`，但当前 AutoResearch 已稳定支持 `success_rate`。
  - `evaluation_metrics.secondary`：`avg_episode_length`、`red_gate_pass_count`、`blue_interception_count`、`escort_distance_error`、`control_smoothness`。
  - `termination_conditions`：红方赛车机穿越所有门、蓝方完成有效拦截、任意硬碰撞、任意出界、`timeout: 600`。
  - `splits`：建议 `train_seeds: [0..99]`、`val_seeds: [100..119]`，M1 实验实际每 trial 取前 3 个 val seed。
- **env.py 需求**：
  - 使用 `src/game_agent/envs/swarm_combat` 的 `EnvConfig`、`SwarmCombatEnv` 或 PettingZoo 兼容 wrapper，配置 `n_red=2`、`n_red_racers=1`、`n_blue=2`、`n_blue_racers=1`、`gate_layout="wide_slalom"`、`max_steps=600`。
  - 需要把 `swarm_combat` 的 agent id、观测、动作和 `info` 字段适配到 ScenarioPackage 合同。`info` 至少包含 `collision`、`out_of_bounds`、`ring_passed_count`/`gate_passed_count`、`communication_dropped`、`action_clipped`。
  - 需要补充确定性 reset、obs/action shape、termination、collision、gate crossing、role assignment 和 timeout 测试。
- **assumptions.md 要点**：
  - 用户未指定通信条件，默认 `perfect`。
  - 用户未指定门数量，`wide_slalom` 采用现有配置的 6 门。
  - 用户未指定具体动力学参数，采用 `swarm_combat.EnvConfig` 默认：赛车机更快，防守机带阻尼且稍慢。
  - 用户未指定胜负优先级，红方主目标定为成功穿门，蓝方通过拦截和阻断影响红方成功率。
  - 用户未指定出生点，采用 `swarm_combat` 固定出生默认，必要时在场景包中写入固定坐标以保证可复现。

## 三、策略包设计

- **推荐算法族**：规则策略优先，具体使用 `SafeRulePolicyAdapter` 风格的安全规则策略；不建议在 M1 直接上 MAPPO。
- **选择理由**：该任务虽是 2v2，但核心是几何路径跟踪、护航距离控制和拦截预测。现有项目 M1 主链路偏向确定性小规模 sweep，规则策略更符合 KISS/YAGNI，可快速验证接口、角色分工和指标闭环。
- **策略架构**：
  - 输入：每个 agent 的固定长度观测向量，加上 `agent_id` 解析 team/role。
  - 输出：单 agent 连续动作，严格 `np.clip(action, low, high)`。
  - 红方赛车机：沿 `wide_slalom` 门序列导航，使用前视目标点和平滑转向。
  - 红方防守机：维持在赛车机与最近蓝方拦截机之间的护航位置，控制护航距离和安全半径。
  - 蓝方赛车机：可作为竞速干扰者或保守穿门者，默认以阻断红方门线为目标。
  - 蓝方防守机：预测红方赛车机下一门路径，执行截击，但通过 safety gate 避免无效碰撞。
  - safety_gate：动作裁剪、边界回推、队内安全距离、敌我碰撞风险前视、NaN/异常回退零动作。
- **搜索空间建议**：
  - `priority_1`：`desired_speed`、`position_gain`、`risk_margin`、`defender_mode`、`intercept_gain`。
  - `priority_2`：`formation_distance`、`turn_lookahead`、`risk_lookahead_steps`、`brake_release_speed`、`protection_weight`。
  - `do_not_tune`：agent 数量、角色数量、`gate_layout`、`max_steps`、action/observation shape、hard constraint 阈值。

## 四、实验方案设计

- **搜索空间大小**：建议先限制为 18 trials。示例 priority_1 组合若为 `desired_speed` 3 档、`intercept_gain` 3 档、`risk_margin` 2 档，笛卡尔积正好 18。
- **推荐 trial 数量**：18，符合当前 `PolicyDesigner.SEARCH_SPACE` 的 M1 预算。
- **seeds 数量**：每个 trial 至少 3 个 seed，建议使用 `val_seeds` 前 3 个，即 `[100, 101, 102]`。
- **预算估计**：`max_steps=600`、4 agent、18 trials、3 seeds，共 54 episodes。规则策略无需真实训练，主要成本在 rollout，预计本地 CPU 数分钟级；若接入可视化或轨迹保存，另行增加预算。
- **晋级标准**：
  - 所有 hard constraints 通过。
  - `success_rate` 相比 baseline 提升至少 0.02。
  - 跨 seed 标准差小于 0.05，或失败 episode 有一致可解释模式。
  - `avg_episode_length` 不显著恶化；同分时优先更短完成时间。

## 五、交接说明

- **Agent 1 -> Agent 2**：
  - 场景包必须冻结 `task_spec.yaml` 中的 agent id、role、observation_space、action_space 和 `env_config`。
  - `reward_structure` 只服务训练/策略设计；`evaluation_metrics` 才是实验排名依据。
  - 若采用 `swarm_combat` 适配层，`env.py` 必须暴露稳定 `make_env(config=None)`，并保证 reset/step 返回结构与现有 hooks 兼容。
- **Agent 2 -> Agent 3**：
  - `policy.py` 必须导出 `PolicyClass`，实现 `contracts.policy_protocol.Policy`。
  - `train.py` 和 `infer.py` CLI 签名保持 `INTERFACE_2_POLICY_TO_AUTORESEARCH.md` 合同要求。
  - `search_space.yaml` 中每个可调字段必须出现在 `get_config_schema()`。
  - `default_config.yaml` 必须包含角色策略参数，不允许实验阶段新增未声明参数。
- **跨阶段约束**：
  - 场景包和策略包一旦写入 `manifest.json.freeze_hash`，下游只读，不回写修改。
  - 不修改 `contracts/`，除非明确决定引入新 `task_family`；本计划默认不修改合同。
  - AutoResearch 排名只读取 `evaluation_metrics` 和 hard constraints，不读取 reward components。

## 六、预期产出

- **`scenarios/wide_slalom_2v2_001/`**：
  - `task_spec.yaml`：2v2 agent 定义、`POSG`、`wide_slalom`、600 步、观测/动作空间、奖励和指标。
  - `env_config.yaml`：`n_red=2`、`n_blue=2`、`n_red_racers=1`、`n_blue_racers=1`、`gate_layout=wide_slalom`、`max_steps=600`。
  - `env.py`：`swarm_combat` 适配层或等价自包含环境。
  - `model.md`：POSG 形式化、角色目标、终止条件。
  - `assumptions.md`：通信、门数量、动力学、出生点和胜负定义的默认值说明。
  - `tests/`：确定性、shape、超时、碰撞、穿门、角色数量测试。
  - `manifest.json`：场景冻结哈希。
- **`policies/wide_slalom_2v2_rule_v1/`**：
  - `policy.py`：安全规则策略，按角色分派 racer/defender 行为。
  - `default_config.yaml`：速度、护航距离、拦截增益、安全边界等默认参数。
  - `search_space.yaml`：18 trial 内的核心搜索空间。
  - `train.py`：规则策略 no-op 训练入口。
  - `infer.py`：按 eval seeds 输出合同格式结果。
  - `algorithm_card.md`：规则策略假设、输入输出、安全机制、失败模式。
  - `tests/` 和 `manifest.json`。
- **`experiments/wide_slalom_2v2_exp_001/`**：
  - `trials/trial_0001..trial_0018/`：每个 trial 的 `config.yaml`、`metrics.json`、`log.json`。
  - `leaderboard.csv`：按 hard constraints、primary metric、episode length 排序。
  - `best_config.yaml`：最优规则参数。
  - `report.md`：结果、失败模式、晋级判断。
  - `manifest.json`。

## 七、风险与未知

- **需要进一步明确的问题**：
  - 红蓝双方是否都要计穿门得分，还是只以红方赛车机成功率为 primary metric。
  - 蓝方赛车机是否也必须穿 `wide_slalom`，还是作为干扰/诱饵参与。
  - 有效拦截的定义：距离阈值、持续步数、是否允许接触式碰撞。
- **当前系统不支持或需扩展的功能**：
  - `src/game_agent/envs/drone_ring_game/env.py` 固定 1v1：`agents = ["red_0", "blue_0"]`，无法直接承接 2v2。
  - 当前 `ScenarioCompiler._build_spec()` 固定输出 1 红 1 蓝和 12 维观测，无法直接从用户文本生成该 2v2 spec。
  - `wide_slalom` 已在 `swarm_combat` 中存在，但不在 `drone_ring_game` 参考环境中接入。
  - 若坚持 `task_family: swarm_combat`，需要修改 `contracts/scenario_schema.yaml` 枚举；本计划为避免合同变更，建议保持 `drone_ring_game` 并在 env_config 中声明 `engine: swarm_combat`。
- **预期失败模式和应对策略**：
  - 红方赛车机在大横向偏移门前振荡：调大 `turn_lookahead`、降低 `desired_speed`。
  - 护航机遮挡己方赛车机路径：增加队内安全距离和护航横向偏置。
  - 蓝方拦截策略通过高碰撞换低成功率：hard constraints 优先，碰撞超阈值 trial 不晋级。
  - 4 agent 观测维度与策略模板不一致：场景冻结前先跑 shape contract tests，再交给 Policy Designer。
  - AutoResearch 指标名不匹配：primary 暂定使用现有 runner 支持的 `success_rate`，避免 `team_score` 尚未接入导致实验失败。

## 八、验证清单

- [x] 用户描述可确定的参数已列出：红蓝各 2 机、角色、`wide_slalom`、600 步。
- [x] 默认值有理由：通信、门数量、动力学、出生点、primary metric。
- [x] `task_id` / `policy_id` / `exp_id` 已推导。
- [x] 已标注当前 1v1 `drone_ring_game` 与 2v2 `wide_slalom` 的能力差距。
- [x] 计划文档满足后续 `game-main` 读取和执行所需的交接信息。
