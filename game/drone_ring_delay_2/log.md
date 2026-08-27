# drone_ring_delay_2 执行日志

## 2026-06-28 — Step 1: 初始化

- **输入**：`game/drone_ring_delay_2/plan.md`
- **task_id**：`drone_ring_delay_2_001`
- **policy_id**：`drone_ring_delay_2_rule_v1`
- **exp_id**：`drone_ring_delay_2_exp_001`
- **目标指标**：`success_rate >= 0.55`
- **断点检查**：待生成场景、策略、实验与可视化产物
- **验证结果**：进入场景编译阶段

## 2026-06-28 — Step 2: 场景编译

- **输入**：`红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 100 步。`
- **输出路径**：`scenarios/drone_ring_delay_2_001/`
- **freeze_hash**：`cc5f50f94961dedc36f604f0fe78891700980542351712fff39194e8039bd8e0`
- **验证结果**：`python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_delay_2_001` 通过
- **重试次数**：0
- **关键落地**：`task_spec.yaml` 写入 `communication.mode=delayed`、`delay_steps=2`、`max_steps=100`

## 2026-06-28 — Step 3: 策略设计

- **输入**：`scenarios/drone_ring_delay_2_001/`
- **输出路径**：`policies/drone_ring_delay_2_rule_v1/`
- **freeze_hash**：`032885c08473bec9e689f4e52996352c5db5ab200a559de91cc548c8f0ce108f`
- **验证结果**：`python src/hooks/post_policy_submit.py --policy policies/drone_ring_delay_2_rule_v1` 通过；`python -m pytest policies/drone_ring_delay_2_rule_v1/tests -v` 为 `5 passed`
- **重试次数**：0
- **关键落地**：在规则策略内固定 `delay_steps=2`，蓝方追击使用 2 步历史观测做滞后拦截，并在近距离触发制动避碰

## 2026-06-28 — Step 4: 首轮实验

- **输入**：`scenarios/drone_ring_delay_2_001/` + `policies/drone_ring_delay_2_rule_v1/`
- **输出路径**：`experiments/drone_ring_delay_2_exp_001/`
- **验证结果**：`python src/hooks/post_experiment_run.py --exp experiments/drone_ring_delay_2_exp_001` 通过
- **trial 数量**：18
- **首轮结论**：参数 sweep 全部满足硬约束，已达到目标指标；best trial 为 `trial_0013`

## 2026-06-28 — Step 5: 策略配置迭代

- **迭代动机**：首轮虽然已达标，但需要让“通信延迟 2 步”不仅体现在场景 spec，也明确体现在策略配置与实验报告中
- **迭代内容**：补充固定参数 `delay_steps=2`、`pursuit_brake_distance=0.35`；保持 `speed_scale / intercept_gain / safety_margin` 为 sweep 旋钮，原地覆盖 18 个 trial 的 config、metrics、log、leaderboard、report 和 manifest
- **best config**：
  - `speed_scale=1.2`
  - `intercept_gain=0.8`
  - `safety_margin=0.1`
  - `delay_steps=2`
  - `pursuit_brake_distance=0.35`
- **best metrics**：`success_rate=1.0`，`collision_rate=0.0`，`out_of_bounds_rate=0.0`，`action_violation_rate=0.0`，`avg_episode_length=26.0`
- **结论**：满足 `success_rate >= 0.55`，并通过全部 hard constraints

## 2026-06-28 — Step 6: 可视化

- **输出路径**：`output/example_02_drone_ring_delay_2.png`
- **可视化内容**：seed 0 下的红方穿环轨迹、蓝方延迟追击轨迹、两个圆环位置，以及最优配置参数摘要
- **检查结果**：PNG 可正常打开，图中红方完成 2 环穿越，episode_length 为 26
