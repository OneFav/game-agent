# drone_ring_basic_1v1 执行汇总

**执行时间**：2026-06-28
**场景来源**：README 示例 1「基础双人穿环」
**目标指标**：`drone_ring_game`，`success_rate >= 0.7`

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功 | `scenarios/drone_ring_basic_1v1_001/` |
| 策略设计 | 成功 | `policies/drone_ring_basic_1v1_rule_v1/` |
| 实验运行 | 成功，18 个 trial 完成 sweep | `experiments/drone_ring_basic_1v1_exp_001/` |
| 2D 可视化 | 成功 | `output/example_01_drone_ring_basic_1v1.png` |

## 场景包

- **路径**：`scenarios/drone_ring_basic_1v1_001/`
- **freeze_hash**：`sha256:3ad2e4c7278ded305c21cc0210789fc2cc6316f9fdd4b8d99b70c222b259310e`
- **关键参数**：`ring_count=2`，`communication.mode=perfect`，`max_steps=60`，`formalism=POSG`
- **验证**：hook 通过；场景包测试 `2 passed`

## 策略包

- **路径**：`policies/drone_ring_basic_1v1_rule_v1/`
- **freeze_hash**：`sha256:b94f9cef2f8b5edb5fc314cd7f9717d64dc1bfe00d24ab767f395417fba0e3c4`
- **算法**：规则策略 `rule_ring_navigation`
- **PolicyClass**：`RuleRingNavigationPolicy`
- **验证**：hook 通过；策略包测试 `5 passed`

## 实验包

- **路径**：`experiments/drone_ring_basic_1v1_exp_001/`
- **freeze_hash**：`sha256:5b140c1a05715581c469f94b76d0685d639acf8e70d5997f081ea78265d1eacc`
- **Trial 总数**：18
- **Best trial**：`trial_0013`
- **Best Config**：`speed_scale=1.2`，`intercept_gain=0.8`，`safety_margin=0.1`
- **Primary Metric**：`success_rate = 1.0`
- **硬约束**：`collision_rate = 0.0`，`out_of_bounds_rate = 0.0`，`action_violation_rate = 0.0`
- **Leaderboard Top 3**：
  1. `trial_0013`：`success_rate=1.0`，`avg_episode_length=26.0`
  2. `trial_0014`：`success_rate=1.0`，`avg_episode_length=26.0`
  3. `trial_0015`：`success_rate=1.0`，`avg_episode_length=26.0`

## 迭代优化结论

- baseline 配置 `trial_0001` 已达到 `success_rate=1.0`，满足目标阈值 `0.7`
- 配置 sweep 进一步验证了 `speed_scale` 是主要影响完成步数的参数
- 将 `speed_scale` 从 `0.8` 提升到 `1.2` 后，保持所有 hard constraints 为 0，同时将 `avg_episode_length` 从 `32.0` 降到 `26.0`
- 结论：示例 1 在当前 M1 规则策略链路下稳定达标，且存在更快完成的可晋级配置

## 可视化产物

- **路径**：`output/example_01_drone_ring_basic_1v1.png`
- **内容**：best trial 的单 seed 2D 轨迹图，包含双环位置、红蓝路径、最优配置参数和终止状态

## 遗留说明

- 当前“迭代优化”通过固定策略源码 + sweep 配置完成，没有引入新的训练脚本或批量总量生成脚本。
- 未修改 `src/contracts/hooks`、`task.md`、其他示例目录，符合本次责任边界。
