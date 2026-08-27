# drone_ring_delay_2 执行汇总

**执行时间**：2026-06-28
**执行模式**：按 `README` 的 `game-init -> game-main -> 继续迭代优化到可视化` 路径完成

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功 | `scenarios/drone_ring_delay_2_001/` |
| 策略设计 | 成功 | `policies/drone_ring_delay_2_rule_v1/` |
| 实验运行 | 成功，18 个 trial 全部完成 | `experiments/drone_ring_delay_2_exp_001/` |
| 可视化输出 | 成功 | `output/example_02_drone_ring_delay_2.png` |

## 场景包

- **路径**：`scenarios/drone_ring_delay_2_001/`
- **freeze_hash**：`cc5f50f94961dedc36f604f0fe78891700980542351712fff39194e8039bd8e0`
- **关键参数**：`ring_count=2`，`max_steps=100`，`communication.mode=delayed`，`delay_steps=2`，`formalism=POSG`
- **验证**：`python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_delay_2_001` 通过

## 策略包

- **路径**：`policies/drone_ring_delay_2_rule_v1/`
- **freeze_hash**：`032885c08473bec9e689f4e52996352c5db5ab200a559de91cc548c8f0ce108f`
- **算法**：规则策略
- **PolicyClass**：`RuleRingNavigationPolicy`
- **延迟建模**：固定 `delay_steps=2`；蓝方使用 2 步历史观测执行滞后追击，近距离触发 `pursuit_brake_distance=0.35` 的制动避碰
- **验证**：`python src/hooks/post_policy_submit.py --policy policies/drone_ring_delay_2_rule_v1` 通过；`python -m pytest policies/drone_ring_delay_2_rule_v1/tests -v` 为 `5 passed`

## 实验包

- **路径**：`experiments/drone_ring_delay_2_exp_001/`
- **freeze_hash**：`52c6c8d2c0079b294b66de01199a782482c2ef911c7881fa573af55504bf284e`
- **Trial 总数**：18
- **优化过程**：围绕 `speed_scale`、`intercept_gain`、`safety_margin` 做全因子 sweep；实验报告已记录 top 3 和前 5 个 hypothesis
- **Best Trial**：`trial_0013`
- **Best Config**：
  - `speed_scale=1.2`
  - `intercept_gain=0.8`
  - `safety_margin=0.1`
  - `delay_steps=2`
  - `pursuit_brake_distance=0.35`
- **Primary Metric**：`success_rate = 1.0`
- **Hard Constraints**：`collision_rate = 0.0`，`out_of_bounds_rate = 0.0`，`action_violation_rate = 0.0`
- **Leaderboard Top 3**：
  1. `trial_0013`: `success_rate = 1.0`, `avg_episode_length = 26.0`
  2. `trial_0014`: `success_rate = 1.0`, `avg_episode_length = 26.0`
  3. `trial_0015`: `success_rate = 1.0`, `avg_episode_length = 26.0`
- **结论**：显著超过目标 `success_rate >= 0.55`

## 可视化产物

- **路径**：`output/example_02_drone_ring_delay_2.png`
- **说明**：图中展示 seed 0 下的红方穿环轨迹、蓝方追击轨迹、环位置及最优参数摘要；红方成功通过两环，终止长度为 26 步

## 迭代结论

- 示例 2 已按指定目录边界落地完成，无需修改共享 `src/contracts/`、`src/hooks/`、`task.md` 或其他示例目录。
- 由于共享 `AutoResearchRunner` 仍直接使用仓库内基线 `DroneRingEnv`，本次“2 步通信延迟”主要在场景 spec 与策略侧观测历史中建模；这一边界已在 `plan.md` 和本汇总中明确记录。
