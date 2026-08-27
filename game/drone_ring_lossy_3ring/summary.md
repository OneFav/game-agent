# drone_ring_lossy_3ring 执行汇总

**执行时间**：2026-06-28
**执行方式**：按 README 示例 3 的单阶段流程完成 `game-init -> compile-scenario -> build-policy -> experiment sweep -> 2D visualization`

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功 | `scenarios/drone_ring_lossy_3ring_001/` |
| 策略设计 | 成功 | `policies/drone_ring_lossy_3ring_rule_v1/` |
| 实验运行 | 成功，完成 18 组 sweep 并晋级最优配置 | `experiments/drone_ring_lossy_3ring_exp_001/` |
| 2D 可视化 | 成功 | `output/example_03_drone_ring_lossy_3ring.png` |

## 场景包

- **路径**：`scenarios/drone_ring_lossy_3ring_001/`
- **freeze_hash**：`7745857b274d8f63b93b0ac43d3fb0abc46f76b39146821231a02e03766ee213`
- **关键参数**：`ring_count=3`，`communication.mode=lossy`，`drop_probability=0.10`，`max_steps=200`，`formalism=POSG`
- **实现要点**：自包含 `DroneRingLossyEnv`，在 12 维观测上对“对手相对状态”和“目标环方向/距离”做 10% 独立掩码，并保持相同 seed 下完全确定
- **验证**：
  - `python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_lossy_3ring_001` → 通过
  - `python -m pytest scenarios/drone_ring_lossy_3ring_001/tests -q` → `3 passed`

## 策略包

- **路径**：`policies/drone_ring_lossy_3ring_rule_v1/`
- **freeze_hash**：`eb8ba1b845d39eed50d888e1bf25676267d95a40a4c0f8ab6d19376e7140d33a`
- **算法**：规则策略
- **PolicyClass**：`RuleRingNavigationPolicy`
- **策略要点**：
  - 红方：直接响应最新目标方向，只有在丢包时才回退到短期记忆
  - 蓝方：预测式追击并带门线偏置，近距离时主动退让以满足碰撞约束
  - `infer.py` 直接评估场景包环境，确保实验指标反映真实 lossy 设定
- **验证**：
  - `python src/hooks/post_policy_submit.py --policy policies/drone_ring_lossy_3ring_rule_v1` → 通过
  - `python -m pytest policies/drone_ring_lossy_3ring_rule_v1/tests -q` → `5 passed`

## 实验包

- **路径**：`experiments/drone_ring_lossy_3ring_exp_001/`
- **freeze_hash**：`1a071fca0f341d669413e594e636e8e27285a5de1ba9c80bf6588a522b54ebf0`
- **Trial 总数**：18
- **迭代结论**：
  - 基线 `trial_0001` 曾先达到 `success_rate = 0.667`
  - 首轮完整 sweep 因观测记忆逻辑过度平滑发生全局退化
  - 修正策略后重跑 sweep，`trial_0013` 晋级为最优
- **Best Config**：
  - `speed_scale: 1.4`
  - `intercept_gain: 0.55`
  - `safety_margin: 0.7`
  - `blue_gate_bias: 0.3`
  - `memory_decay: 0.85`
  - `recovery_gain: 1.1`
- **Primary Metric**：`success_rate = 1.0`
- **Hard Constraints**：`collision_rate = 0.0`，`out_of_bounds_rate = 0.0`，`action_violation_rate = 0.0`
- **Leaderboard Top 3**：
  1. `trial_0013` → `success_rate = 1.0`, `avg_episode_length = 35.33`
  2. `trial_0015` → `success_rate = 1.0`, `avg_episode_length = 35.33`
  3. `trial_0017` → `success_rate = 1.0`, `avg_episode_length = 35.33`
- **验证**：
  - `python src/hooks/post_experiment_run.py --exp experiments/drone_ring_lossy_3ring_exp_001` → 通过

## 可视化落地

- **输出文件**：`output/example_03_drone_ring_lossy_3ring.png`
- **内容**：最佳配置在 seed `0` 下的 2D 红蓝轨迹、三环位置、起终点以及发生丢包观测的步点标记
- **结论**：示例 3 不仅满足目标 `success_rate >= 0.4`，还在 18 组配置 sweep 后达到 `success_rate = 1.0`

## 备注

- 本任务未修改 `src/contracts/`、`src/hooks/`、`task.md` 或其他示例目录。
- 根级 `CLAUDE.md` 与 `INTERFACE_*.md` 缺失，执行过程中已以 `docs/CLAUDE.md`、现有 hooks、contracts、CLI 和参考产物补齐约束来源。
