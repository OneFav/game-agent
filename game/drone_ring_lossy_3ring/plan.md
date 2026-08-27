# drone_ring_lossy_3ring 实施计划

## 一、需求分析

- **任务族**：`drone_ring_game`
- **场景描述摘要**：红方无人机需要依次穿过三个圆环，蓝方无人机负责追击拦截；通信存在 `10%` 丢包，episode 超时上限为 `200` 步。
- **形式化定义**：`formalism: POSG`。红蓝双方同时决策，红方主目标是最大化穿环成功率并尽快完成，蓝方主目标是通过几何追击阻断红方路径。通信噪声会影响双方对对手和目标环方向的利用，因此策略必须兼顾鲁棒性与安全边界。
- **关键参数表**：
  - `game_id`: `drone_ring_lossy_3ring`
  - `task_id`: `drone_ring_lossy_3ring_001`
  - `policy_id`: `drone_ring_lossy_3ring_rule_v1`
  - `exp_id`: `drone_ring_lossy_3ring_exp_001`
  - `ring_count`: 3
  - `communication.mode`: `lossy`
  - `communication.drop_probability`: `0.10`
  - `max_steps`: 200
  - `primary_metric`: `success_rate`
  - `target_metric`: `success_rate >= 0.4`
  - `hard_constraints`: `collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate <= 0.0`

## 二、场景包设计

- **task_spec.yaml 设计要点**：
  - 保持 `task_family: drone_ring_game`、`formalism: POSG`、双智能体 `red_0` / `blue_0`。
  - `observation_space` 保持 `[12]`，与当前 `drone_ring_game` 参考环境和策略模板兼容。
  - `action_space` 保持 `[4]`，前两维为 2D 速度/加速度指令，后两维保留接口兼容位。
  - `reward_structure` 与 `evaluation_metrics` 保持解耦，primary metric 继续使用 `success_rate`，避免 reward hacking。
  - `termination_conditions` 包含红方完成三环、蓝方碰撞拦截、任一方出界以及超时。
  - `communication` 必须显式记录 `lossy` 和 `drop_probability=0.10`。
- **env.py 需求**：
  - 以现有 `src/game_agent/envs/drone_ring_game/env.py` 的 1v1 机制为基底，在场景目录实现自包含版本。
  - 在场景环境中真实注入丢包：对观测中的对手相对量和目标环方向进行有种子控制的随机丢失/保持，保证 `reset(seed)` 和 `step()` 在相同 seed 下完全确定。
  - `info["metrics"]` 之外，还要提供 `collision`、`out_of_bounds`、`ring_passed_count`、`communication_dropped`、`action_clipped` 等信息，以符合 skill 要求并支持后续可视化。
  - 包内测试至少覆盖确定性、obs/action shape 和丢包字段存在性。
- **assumptions.md 要点**：
  - 用户未指定动力学模型，采用当前 M1 轻量 2D 点质量双积分近似。
  - 用户未指定边界和环半径，沿用项目基线并在说明中记录理由。
  - 用户未指定蓝方通信是否同样丢包，默认双方共享同一通信噪声模型。

## 三、策略包设计

- **推荐算法族**：规则策略
- **选择理由**：示例 3 仍属于当前 M1 已支持的 `drone_ring_game` 变体，规则策略即可完成可验证闭环，不需要引入学习型训练或新算法代码，符合 KISS / YAGNI。
- **策略架构**：
  - 红方策略围绕“稳态前视穿环 + 近距离避碰 + 丢包退化补偿”设计。
  - 蓝方策略围绕“预测式拦截 + 距离门线阻断 + 安全缓冲”设计。
  - 在 `policy.py` 中根据 `agent_id` 分流红蓝行为，统一在末端执行 `np.clip`。
  - 对观测缺失场景提供保守回退：若关键特征丢失，则延续上一时刻方向或采用零侧向纠偏，避免在丢包帧产生大幅振荡。
- **搜索空间建议**：
  - `priority_1`：`red_speed_scale`、`blue_intercept_gain`、`red_avoidance_gain`
  - `priority_2`：`ring_lookahead_gain`、`blue_gate_bias`、`memory_decay`
  - `do_not_tune`：动作边界、观测维度、hard constraint 阈值、环数量、超时步数、丢包率

## 四、实验方案设计

- **搜索空间大小**：优先控制在 `12` 到 `18` 个 trial，先只扫 `priority_1`。
- **推荐 trial 数量**：初始 12，若指标不足再追加针对性 trial。
- **seeds 数量**：每个 trial 至少 3 个 seed，优先 `0, 1, 2`。
- **预算估计**：规则策略无需真实训练，主要成本是 rollout，示例 3 在本地 CPU 上应为分钟级。
- **晋级标准**：
  - 所有 hard constraints 通过。
  - `success_rate` 达到或超过 `0.4`。
  - 若多个 trial 同样过线，优先 `avg_episode_length` 更短者。
  - 若不过线，必须基于失败模式调整策略配置或策略逻辑，并在 `log.md` 与 `summary.md` 记录迭代原因。

## 五、交接说明

- **Agent 1 → Agent 2**：
  - 场景包冻结 `task_spec.yaml`、`env_config.yaml`、`env.py`、`assumptions.md` 和 `manifest.json`。
  - 观测中的丢包语义必须在 `model.md` 和 `assumptions.md` 讲清楚，便于策略解释为什么需要记忆与回退。
- **Agent 2 → Agent 3**：
  - `PolicyClass` 必须实现 `contracts.policy_protocol.Policy`。
  - `train.py`、`infer.py` 的 CLI 签名保持现有 contract 兼容。
  - `search_space.yaml` 中所有调参字段必须出现在 `get_config_schema()` 中。
- **跨阶段约束**：
  - 不修改 `src/contracts/`、`src/hooks/`、`task.md`、其他示例目录。
  - 仅允许写入 `game/drone_ring_lossy_3ring/`、`scenarios/drone_ring_lossy_3ring_001/`、`policies/drone_ring_lossy_3ring_rule_v1/`、`experiments/drone_ring_lossy_3ring_exp_001/`、`output/example_03_drone_ring_lossy_3ring.png`。
  - 仓库中缺少根级 `CLAUDE.md` 与两份 `INTERFACE_*.md`；本任务以 `docs/CLAUDE.md`、现有 hooks、contracts、CLI 与参考产物作为事实来源，不额外扩展共享合同。

## 六、预期产出

- **`scenarios/drone_ring_lossy_3ring_001/`**：
  - `task_spec.yaml`、`env_config.yaml`、`env.py`、`model.md`、`assumptions.md`、`tests/`、`manifest.json`
  - 明确三环、10% 丢包、200 步超时和 hard constraints
- **`policies/drone_ring_lossy_3ring_rule_v1/`**：
  - `policy.py`、`train.py`、`infer.py`、`default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`requirements.txt`、`tests/`、`metadata.json`、`manifest.json`
  - 规则策略要对丢包观测具备退化鲁棒性
- **`experiments/drone_ring_lossy_3ring_exp_001/`**：
  - `trials/`、`leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`
  - 记录每次 trial 假设、指标和排序结果
- **`output/example_03_drone_ring_lossy_3ring.png`**：
  - 2D 可视化，展示最佳配置下红蓝轨迹、三个圆环和关键事件

## 七、风险与未知

- **需要进一步明确的问题**：
  - 当前 M1 合约并未强制定义通信丢包如何作用于观测；本任务采用“局部观测字段随机保留/清零”的可重复实现。
  - `post_scenario_compile.py` 不验证通信语义真实性，因此需要通过 `model.md`、`assumptions.md`、实验报告和可视化补足说明。
- **当前系统边界**：
  - AutoResearch runner 只按 `evaluation_metrics` 排名，且默认使用 `DroneRingEnv`；若要让实验真实反映 lossy 环境，需要实验包在本地自管 rollout 逻辑或确保 infer 阶段单独复核。
  - 参考 `PolicyDesigner` 的默认模板字段较少，示例 3 需要在策略目录内扩展更细的规则参数，但仍需保持 hook 兼容。
- **预期失败模式和应对策略**：
  - 红方在连续丢包时对环方向估计失真，导致中段振荡。应对：引入短期记忆与目标方向衰减。
  - 蓝方过强拦截导致碰撞率超阈。应对：增加门线偏置或降低 intercept gain。
  - 成功率不足 0.4。应对：基于 leaderboard 与逐 seed 失败模式追加定向 sweep，不扩大到新的算法族。

## 八、验证清单

- [x] 示例 3 已映射为 `drone_ring_game`
- [x] `task_id / policy_id / exp_id` 已固定
- [x] 所有默认值与缺失合同已在计划中说明
- [x] 仅限写入目录已固定
- [x] 计划文档超过 500 字，可直接供 `game-main` 执行
