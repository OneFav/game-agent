# figure_eight_4v4 执行日志

## 2026-06-28 — Step 1: game-init 规划

- **输入**：README 示例 7 原始 prompt
- **输出路径**：`game/figure_eight_4v4/plan.md`
- **task_id**：`figure_eight_4v4_001`
- **policy_id**：`figure_eight_4v4_rule_v1`
- **exp_id**：`figure_eight_4v4_exp_001`
- **验证结果**：完成需求抽取与边界核对
- **备注**：共享 `scenario_schema.yaml` 与 `autoresearch/runner.py` 仍偏向 `drone_ring_game`，后续将以同一三阶段接口输出 `swarm_combat` 适配包。

## 2026-06-28 — Step 2: 场景编译

- **输入**：红蓝双方各 4 机、`figure_eight`、双向穿门、`DampedDoubleIntegrator3D`、1200 步
- **输出路径**：`scenarios/figure_eight_4v4_001/`
- **freeze_hash**：`f77f54fd349f1e4d61d71f5e5d9ff2c8247ec180fbd05ce5cbd4974f60ec5514`
- **验证结果**：通过，`python src/hooks/post_scenario_compile.py --scenario scenarios/figure_eight_4v4_001`
- **包内测试**：`python -m pytest scenarios/figure_eight_4v4_001/tests -v` → `2 passed`
- **折中说明**：共享 schema 仍写 `task_family: drone_ring_game`；真实 4v4 3D `swarm_combat` 语义冻结在 `env.py` 与 `env_config.yaml`

## 2026-06-28 — Step 3: 策略设计

- **输入**：`scenarios/figure_eight_4v4_001/`
- **输出路径**：`policies/figure_eight_4v4_rule_v1/`
- **freeze_hash**：`8b6abee20c9b15157ed033e9b16ca6fcc060fa7d25c19425d72dbc3536b997dd`
- **验证结果**：通过，`python src/hooks/post_policy_submit.py --policy policies/figure_eight_4v4_rule_v1`
- **包内测试**：`python -m pytest policies/figure_eight_4v4_rule_v1/tests -v` → `4 passed`
- **策略说明**：复用 `SafeRulePolicy` 的前瞻避碰与多 racer 分道逻辑，按 `compute_actions(env)` 驱动真实 8 机 3D 环境

## 2026-06-28 — Step 4: 实验运行与迭代优化

- **输入**：`scenarios/figure_eight_4v4_001/` + `policies/figure_eight_4v4_rule_v1/`
- **输出路径**：`experiments/figure_eight_4v4_exp_001/`
- **freeze_hash**：`7735fc1b554f28ba98dc77a8d31a52b3b81f34a1ab3697a68ff589e7fe88fc7c`
- **实验方式**：按 `desired_speed x lane_spacing x turn_lookahead x risk_margin x defender_mode` 全量笛卡尔积执行 12 个 trial，每个 trial 使用 `100,101,102` 三个 seed
- **最佳 trial**：`trial_0001`
- **最佳配置**：`desired_speed=5.4`，`lane_spacing=1.4`，`turn_lookahead=6.0`，`risk_margin=0.9`，`defender_mode=escort`
- **最佳指标**：`team_score=4.0`，`blue_team_score=0.0`，`collision_rate=0.0`，`out_of_bounds_rate=0.0`，`action_violation_rate=0.0`
- **验证结果**：通过，`python src/hooks/post_experiment_run.py --exp experiments/figure_eight_4v4_exp_001`
- **阶段说明**：共享 `src/game_agent/autoresearch/runner.py` 固定绑定 `DroneRingEnv`，因此本阶段在 experiment 包内按相同三阶段接口产出自适配 ExperimentPackage，而不是修改共享 runner

## 2026-06-28 — Step 5: 3D 可视化落地

- **输入**：`experiments/figure_eight_4v4_exp_001/best_config.yaml`
- **输出路径**：`output/example_07_figure_eight_4v4.png`
- **执行命令**：`python experiments/figure_eight_4v4_exp_001/visualize_best_trial.py`
- **结果**：生成 3D 轨迹总览 PNG，展示门布局、轨迹、比分与穿门次数
