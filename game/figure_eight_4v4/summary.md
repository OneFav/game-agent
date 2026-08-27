# figure_eight_4v4 执行汇总

**执行时间**：2026-06-28（当前轮完成 `game-init -> game-main -> 参数迭代 -> 3D 可视化`）

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功 | `scenarios/figure_eight_4v4_001/` |
| 策略设计 | 成功 | `policies/figure_eight_4v4_rule_v1/` |
| 实验运行 | 成功，完成 12 个 trial 全量 sweep | `experiments/figure_eight_4v4_exp_001/` |
| 3D 可视化 | 成功 | `output/example_07_figure_eight_4v4.png` |

## 场景包

- **路径**：`scenarios/figure_eight_4v4_001/`
- **freeze_hash**：`f77f54fd349f1e4d61d71f5e5d9ff2c8247ec180fbd05ce5cbd4974f60ec5514`
- **关键参数**：红方 4 机、蓝方 4 机，`gate_layout=figure_eight`，`DampedDoubleIntegrator3D`，`max_steps=1200`，`communication.mode=perfect`，`formalism=POSG`
- **适配说明**：共享 `scenario_schema.yaml` 仍只支持 `drone_ring_game`。本次没有修改共享合同，而是在场景包内通过 wrapper 固化真实 `swarm_combat` 4v4 3D 语义。
- **验证**：`python src/hooks/post_scenario_compile.py --scenario scenarios/figure_eight_4v4_001` 通过；场景包测试 `2 passed`

## 策略包

- **路径**：`policies/figure_eight_4v4_rule_v1/`
- **freeze_hash**：`8b6abee20c9b15157ed033e9b16ca6fcc060fa7d25c19425d72dbc3536b997dd`
- **算法**：规则策略，包装 `SafeRulePolicy`
- **PolicyClass**：`FigureEight4v4RulePolicy`
- **默认配置**：`desired_speed=5.8`，`lane_spacing=1.4`，`turn_lookahead=6.0`，`risk_margin=0.9`
- **验证**：`python src/hooks/post_policy_submit.py --policy policies/figure_eight_4v4_rule_v1` 通过；包内测试 `4 passed`

## 实验包

- **路径**：`experiments/figure_eight_4v4_exp_001/`
- **freeze_hash**：`7735fc1b554f28ba98dc77a8d31a52b3b81f34a1ab3697a68ff589e7fe88fc7c`
- **Trial 总数**：12
- **实验方式**：对 `desired_speed x lane_spacing x turn_lookahead x risk_margin x defender_mode` 做全量笛卡尔积 sweep，每个 trial 用 3 个 seed
- **Best Config**：
  - `desired_speed: 5.4`
  - `lane_spacing: 1.4`
  - `turn_lookahead: 6.0`
  - 其余参数保持 `default_config.yaml`
- **Primary Metric**：`team_score = 4.0`
- **Leaderboard Top 3**：
  1. `trial_0001`: `team_score=4.0`, `collision_rate=0.0`, `avg_episode_length=1200.0`
  2. `trial_0002`: `team_score=4.0`, `collision_rate=0.0`, `avg_episode_length=1200.0`
  3. `trial_0003`: `team_score=4.0`, `collision_rate=0.0`, `avg_episode_length=1200.0`
- **目标结论**：满足 README 示例 7 目标，`swarm_combat` 口径下 `team_score >= 4.0`
- **验证**：`python src/hooks/post_experiment_run.py --exp experiments/figure_eight_4v4_exp_001` 通过

## 迭代结论

- 本轮没有修改共享 `src/contracts`、`src/hooks` 或 `task.md`。
- 共享 `game-init/game-main` 的直接边界不足以原生运行 `swarm_combat` 4v4 3D，因为 schema 和 runner 仍绑定旧合同；本次已在 plan/log/summary 中明确说明，并通过同一三阶段接口产出适配场景包、策略包和实验包。
- Sweep 结果表明：更激进的速度组合虽然也能拿到 `team_score=4.0`，但会触发碰撞硬约束；保守配置 `desired_speed=5.4`、`lane_spacing=1.4`、`turn_lookahead=6.0` 是当前最稳的可晋级解。

## 可视化落地

- **PNG 输出**：`output/example_07_figure_eight_4v4.png`
- **复现命令**：`python experiments/figure_eight_4v4_exp_001/visualize_best_trial.py`
