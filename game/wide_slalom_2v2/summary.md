# wide_slalom_2v2 执行汇总

**执行时间**：2026-06-28
**执行模式**：按 README 示例 5，完成 `game-init -> game-main -> 迭代优化 -> 3D 可视化`

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功（从旧 2D 壳迁移到真实 `swarm_combat` wrapper） | `scenarios/wide_slalom_2v2_001/` |
| 策略设计 | 成功（team-aware `SafeRulePolicy` 适配） | `policies/wide_slalom_2v2_rule_v1/` |
| 实验运行 | 成功（9 trial `team_score` sweep） | `experiments/wide_slalom_2v2_exp_001/` |
| 可视化输出 | 成功 | `output/example_05_wide_slalom_2v2.png` |

## 场景包

- **路径**：`scenarios/wide_slalom_2v2_001/`
- **freeze_hash**：`sha256:7b67da025e98b7d81ca5a9465c4cb9a0cd8ba31fca7f564cdb130f2d8e7839dc`
- **关键参数**：`task_family=swarm_combat`，`gate_layout=wide_slalom`，`max_steps=600`，`n_red=2`，`n_blue=2`，`gate_pass_reward=1.0`
- **说明**：场景 wrapper 将共享 `SwarmCombatEnv` 暴露为本地四机命名接口，并通过 `info["raw_env"]` 供策略直接消费真实 3D 环境状态

## 策略包

- **路径**：`policies/wide_slalom_2v2_rule_v1/`
- **freeze_hash**：`sha256:32fa71d47f16fcd4caa5e15a28f30cd57d82662fac53b395a10cff87682cf908`
- **算法**：规则策略 / team-aware `SafeRulePolicy`
- **默认配置**：
  - `desired_speed=5.0`
  - `risk_margin=0.9`
  - `position_gain=1.2`
  - `velocity_gain=2.2`
- **说明**：红 defender 固定 escort，蓝 defender 固定 intercept；无 `raw_env` 时退回 observation-only fallback，以保持 hook/test 兼容

## 实验包

- **路径**：`experiments/wide_slalom_2v2_exp_001/`
- **freeze_hash**：`sha256:9d84ef0083b41b0143a99c47988a14f22ceacf6f4a0461c61d89db18ccee3599`
- **Trial 总数**：9
- **Best Trial**：`trial_0008`
- **Best Config**：
  - `desired_speed=5.0`
  - `risk_margin=0.9`
  - 其余参数维持当前默认值
- **Primary Metric**：`team_score = 6.0`
- **空场测试**：
  - `U_R(红,∅)=6.0`
  - `U_R(红,真蓝)=-1.0`
  - `Delta(coupling load)=7.0`
  - 判定：通过（`Delta > 0`）
- **Hard Constraints**：
  - `collision_rate = 0.0`
  - `out_of_bounds_rate = 0.0`
  - `action_violation_rate = 0.0`
- **Secondary**：
  - `avg_red_score = 6.0`
  - `avg_blue_score = 7.0`
  - `avg_episode_length = 600.0`
- **Leaderboard Top 3**：
  1. `trial_0008`: `team_score=6.0`, feasible, `decision=promote`
  2. `trial_0009`: `team_score=6.0`, feasible, `decision=continue`
  3. `trial_0004`: `team_score=3.0`, feasible, `decision=continue`

## 迭代结论

- 旧版 `drone_ring_game + success_rate` 断点产物不满足示例 5 的真实需求，已被局部替换为 `swarm_combat + team_score` 链路。
- 第一轮 pilot 暴露了两个关键问题：共享策略没有按 episode reset；出生点过紧造成 gate collision。修正后，`desired_speed=5.0`、`risk_margin=0.9` 稳定达到 `team_score=6.0 >= 2.0` 且三项硬约束全部通过。
- 当前主指标采用“红方累计队伍得分”口径，蓝方得分与 winner 仍保留在 secondary 指标和 `per_seed_metrics` 中，便于后续继续定义更严格的对抗排名规则。

## 可视化产物

- `experiments/wide_slalom_2v2_exp_001/trajectory_3d_seed100.png`
- `experiments/wide_slalom_2v2_exp_001/topdown_seed100.png`
- `output/example_05_wide_slalom_2v2.png`
