# wide_slalom_2v2 执行日志

## 2026-06-28 — Step 1: 断点审计 / game-init 复核

- **输入**：README 示例 5 prompt，既有 `wide_slalom_2v2` 断点产物
- **检查结论**：
  - 旧场景包仍是 `task_family=drone_ring_game`
  - 旧实验主指标仍是 `success_rate`
  - 与本次目标 `swarm_combat + team_score >= 2.0` 不一致
- **处理决策**：保留目录作为断点基础，但在允许范围内重写场景、策略和实验包

## 2026-06-28 — Step 2: 场景迁移 / game-main Stage 1

- **输出路径**：`scenarios/wide_slalom_2v2_001/`
- **关键变更**：
  - 将 `task_spec.yaml` 切换为 `task_family=swarm_combat`
  - `env.py` 改为真实 3D `SwarmCombatEnv` thin wrapper
  - 保留本地 4 维动作兼容层，前 3 维映射到 XYZ 加速度
  - 固定出生点调整为 `(-20, ±8, 4.5)` / `(20, ±8, 4.5)` 对称布局
- **验证**：
  - `python src/hooks/post_scenario_compile.py --scenario scenarios/wide_slalom_2v2_001` → 通过
  - `python -m pytest scenarios/wide_slalom_2v2_001/tests -v` → `3 passed`
- **freeze_hash**：`sha256:7b67da025e98b7d81ca5a9465c4cb9a0cd8ba31fca7f564cdb130f2d8e7839dc`

## 2026-06-28 — Step 3: 策略迁移 / game-main Stage 2

- **输出路径**：`policies/wide_slalom_2v2_rule_v1/`
- **关键变更**：
  - 本地 `PolicyClass` 改为 team-aware 适配器
  - 运行时从 `info["raw_env"]` 读取共享 3D 环境，复用 `SafeRulePolicy`
  - 红 defender 固定 escort，蓝 defender 固定 intercept
  - 默认配置提升到当前最优点：`desired_speed=5.0`, `risk_margin=0.9`
- **验证**：
  - `python src/hooks/post_policy_submit.py --policy policies/wide_slalom_2v2_rule_v1` → 通过
  - `python -m pytest policies/wide_slalom_2v2_rule_v1/tests -v` → `5 passed`
- **freeze_hash**：`sha256:32fa71d47f16fcd4caa5e15a28f30cd57d82662fac53b395a10cff87682cf908`

## 2026-06-28 — Step 4: Pilot 校验 / 迭代 0

- **产物路径**：`experiments/wide_slalom_2v2_exp_001/_smoke/`
- **目的**：先验证 `train.py + infer.py` 的 `team_score` 口径是否闭环
- **第一次失败定位**：
  - 策略 wrapper 未在 episode 开始时调用共享 `SafeRulePolicy.reset(env)`
  - 紧凑出生点 `(-20, ±4)` 导致 gate collision
- **修正**：
  - 在 `PolicyClass.reset()` / `_act_from_env()` 接入真实 env reset
  - 出生点改回共享基线可行的 `(-20, ±8, 4.5)` / `(20, ±8, 4.5)`
- **校验结果**：pilot 重新运行后，候选配置 `desired_speed=5.0, risk_margin=0.9` 达到 `team_score=6.0` 且全部硬约束通过

## 2026-06-28 — Step 5: 9 Trial Sweep / game-main Stage 3

- **输出路径**：`experiments/wide_slalom_2v2_exp_001/`
- **搜索空间**：
  - `desired_speed ∈ {4.0, 4.5, 5.0}`
  - `risk_margin ∈ {0.75, 0.9, 1.05}`
- **执行方式**：逐 trial 调用本地 `train.py` 与 `infer.py`，写回 `config.yaml`、`checkpoint/checkpoint.json`、`infer_results.json`、`metrics.json`、`log.json`
- **Top 5**：
  1. `trial_0008` → `team_score=6.0`, `collision_rate=0.0`, `decision=promote`
  2. `trial_0009` → `team_score=6.0`, `collision_rate=0.0`, `decision=continue`
  3. `trial_0004` → `team_score=3.0`, `collision_rate=0.0`, `decision=continue`
  4. `trial_0006` → `team_score=3.0`, `collision_rate=0.0`, `decision=continue`
  5. `trial_0007` → `team_score=3.0`, `collision_rate=0.0`, `decision=continue`
- **Rollback Trial**：
  - `trial_0001`, `trial_0002`, `trial_0003`, `trial_0005` 因碰撞率 1.0 回退
- **验证**：
  - `python src/hooks/post_experiment_run.py --exp experiments/wide_slalom_2v2_exp_001` → 通过
- **freeze_hash**：`sha256:73f778625db9d974524d0d26ced51e2fbf563f57a171e7d86363a56eaba8f9a9`

## 2026-06-28 — Step 6: 可视化与最终核验

- **可视化脚本**：`experiments/wide_slalom_2v2_exp_001/visualize_best_trial.py`
- **输出**：
  - `experiments/wide_slalom_2v2_exp_001/trajectory_3d_seed100.png`
  - `experiments/wide_slalom_2v2_exp_001/topdown_seed100.png`
  - `output/example_05_wide_slalom_2v2.png`
- **最终验证**：
  - `python src/hooks/post_scenario_compile.py --scenario scenarios/wide_slalom_2v2_001` → 通过
  - `python src/hooks/post_policy_submit.py --policy policies/wide_slalom_2v2_rule_v1` → 通过
  - `python src/hooks/post_experiment_run.py --exp experiments/wide_slalom_2v2_exp_001` → 通过
  - `python -m pytest scenarios/wide_slalom_2v2_001/tests -v` → `3 passed`
  - `python -m pytest policies/wide_slalom_2v2_rule_v1/tests -v` → `5 passed`

## 2026-06-30 — Step 7: 空场测试 / 博弈存在性门禁

- **输入**：`trial_0008` best config，seeds `100,101,102`
- **效用定义**：`U_R = red_score - blue_score`
- **空场条件**：蓝方出生点移到远离门场的固定位置并强制零动作；红方策略、场景 wrapper、best config 和 seeds 保持不变
- **结果**：
  - `U_R(红,∅)=6.000`
  - `U_R(红,真蓝)=-1.000`
  - `Delta(coupling load)=7.000`
- **验证结果**：通过，`Delta > 0`
- **输出路径**：`experiments/wide_slalom_2v2_exp_001/coupling_load_test.json`
- **更新后的 experiment freeze_hash**：`sha256:9d84ef0083b41b0143a99c47988a14f22ceacf6f4a0461c61d89db18ccee3599`
