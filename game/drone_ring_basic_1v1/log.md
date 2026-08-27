# drone_ring_basic_1v1 执行日志

## 2026-06-28 — Step 1: 初始化

- **输入**：示例 1 prompt「红方无人机穿过两个圆环，蓝方追击拦截，完美通信，超时 60 步」
- **task_id**：`drone_ring_basic_1v1_001`
- **policy_id**：`drone_ring_basic_1v1_rule_v1`
- **exp_id**：`drone_ring_basic_1v1_exp_001`
- **目标**：`drone_ring_game`，`success_rate >= 0.7`
- **执行方式**：按 `game-init -> game-main -> 迭代优化配置 -> 2D 可视化`
- **断点检查**：目标场景、策略、实验、输出 PNG 均不存在，允许从空目录开始生成

## 2026-06-28 — Step 2: 场景编译

- **输入**：`python -m game_agent.cli compile-scenario --task "红方无人机穿过两个圆环，蓝方追击拦截，完美通信，超时 60 步。" --task-id "drone_ring_basic_1v1_001"`
- **输出路径**：`scenarios/drone_ring_basic_1v1_001/`
- **freeze_hash**：`sha256:3ad2e4c7278ded305c21cc0210789fc2cc6316f9fdd4b8d99b70c222b259310e`
- **验证结果**：`python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_basic_1v1_001` 通过；包内测试 `2 passed`
- **重试次数**：0
- **修正记录**：编译器初版把 perfect communication 记成默认值，随后仅在目标场景目录内修正 `assumptions.md` 文案并重建 manifest，未改共享源码。

## 2026-06-28 — Step 3: 策略设计

- **输入**：`python -m game_agent.cli build-policy --scenario scenarios/drone_ring_basic_1v1_001 --policy-id "drone_ring_basic_1v1_rule_v1"`
- **输出路径**：`policies/drone_ring_basic_1v1_rule_v1/`
- **freeze_hash**：`sha256:b94f9cef2f8b5edb5fc314cd7f9717d64dc1bfe00d24ab767f395417fba0e3c4`
- **验证结果**：`python src/hooks/post_policy_submit.py --policy policies/drone_ring_basic_1v1_rule_v1` 通过；包内测试 `5 passed`
- **重试次数**：0
- **策略说明**：维持规则策略模板，不改策略源码；调优责任放在 `search_space.yaml` 的 18 组配置 sweep。

## 2026-06-28 — Step 4: 实验运行

- **输入**：`python -m game_agent.cli run-experiment --scenario scenarios/drone_ring_basic_1v1_001 --policy policies/drone_ring_basic_1v1_rule_v1 --exp-id "drone_ring_basic_1v1_exp_001"`
- **输出路径**：`experiments/drone_ring_basic_1v1_exp_001/`
- **freeze_hash**：`sha256:5b140c1a05715581c469f94b76d0685d639acf8e70d5997f081ea78265d1eacc`
- **验证结果**：`python src/hooks/post_experiment_run.py --exp experiments/drone_ring_basic_1v1_exp_001` 通过
- **重试次数**：0
- **trial 数量**：18
- **baseline trial**：`trial_0001`，`speed_scale=0.8`，`intercept_gain=0.8`，`safety_margin=0.1`，`success_rate=1.0`，`avg_episode_length=32.0`
- **best trial**：`trial_0013`，`speed_scale=1.2`，`intercept_gain=0.8`，`safety_margin=0.1`，`success_rate=1.0`，`avg_episode_length=26.0`
- **迭代结论**：主指标从基线开始已达标，但通过提高 `speed_scale` 将平均完成步数从 32 降到 26；全部试验均满足 `collision_rate=0.0`、`out_of_bounds_rate=0.0`、`action_violation_rate=0.0`。

## 2026-06-28 — Step 5: 2D 可视化落地

- **输入**：`best_config.yaml` + `seed=0` rollout
- **输出路径**：`output/example_01_drone_ring_basic_1v1.png`
- **内容**：绘制两个圆环、红方轨迹、蓝方轨迹、最优配置参数和 rollout 终态
- **结果**：PNG 已生成并人工检查可读，展示 `trial_0013` 在 26 步内成功完成双环任务
