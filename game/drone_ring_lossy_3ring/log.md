# drone_ring_lossy_3ring 执行日志

## 2026-06-28 — Step 1: game-init

- **输入**：示例 3 原始 prompt：`红方无人机穿过三个圆环，蓝方追击拦截，丢包 10%，超时 200 步。`
- **输出**：`game/drone_ring_lossy_3ring/plan.md`
- **task_id**：`drone_ring_lossy_3ring_001`
- **policy_id**：`drone_ring_lossy_3ring_rule_v1`
- **exp_id**：`drone_ring_lossy_3ring_exp_001`
- **仓库事实**：`docs/CLAUDE.md` 存在；根级 `CLAUDE.md`、`INTERFACE_1_SCENARIO_TO_POLICY.md`、`INTERFACE_2_POLICY_TO_AUTORESEARCH.md` 缺失，后续以现有 `README.md`、`contracts/`、`hooks/`、CLI 与参考产物为执行依据
- **状态**：完成，进入 `game-main`

## 2026-06-28 — Step 2: 场景编译

- **执行入口**：`python -m game_agent compile-scenario --project-root . --task "<示例 3 prompt>" --task-id drone_ring_lossy_3ring_001`
- **输出路径**：`scenarios/drone_ring_lossy_3ring_001/`
- **二次实现**：将模板 fallback stub 替换成自包含 `DroneRingLossyEnv`，加入三环交替布局、10% 丢包观测掩码、确定性随机序列和完整 info 字段
- **场景测试**：`python -m pytest scenarios/drone_ring_lossy_3ring_001/tests -q` → `3 passed`
- **Hook**：`python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_lossy_3ring_001` → `passed`
- **freeze_hash**：`7745857b274d8f63b93b0ac43d3fb0abc46f76b39146821231a02e03766ee213`

## 2026-06-28 — Step 3: 策略设计

- **执行入口**：`python -m game_agent build-policy --project-root . --scenario drone_ring_lossy_3ring_001 --policy-id drone_ring_lossy_3ring_rule_v1`
- **输出路径**：`policies/drone_ring_lossy_3ring_rule_v1/`
- **二次实现**：将通用规则策略收紧为“丢包时用记忆回退、有值时直接响应”的鲁棒穿环/拦截策略；`infer.py` 改为直接基于场景包环境评估，不再回退到共享 perfect-comm runner
- **策略测试**：`python -m pytest policies/drone_ring_lossy_3ring_rule_v1/tests -q` → `5 passed`
- **Hook**：`python src/hooks/post_policy_submit.py --policy policies/drone_ring_lossy_3ring_rule_v1` → `passed`
- **freeze_hash**：`eb8ba1b845d39eed50d888e1bf25676267d95a40a4c0f8ab6d19376e7140d33a`

## 2026-06-28 — Step 4: 基线评估

- **trial**：`trial_0001`（默认配置）
- **命令**：
  - `python policies/drone_ring_lossy_3ring_rule_v1/train.py --config .../trial_0001/config.yaml --scenario scenarios/drone_ring_lossy_3ring_001 --seed 0 --output_dir .../trial_0001 --max_steps 200 --wall_time_limit 30`
  - `python policies/drone_ring_lossy_3ring_rule_v1/infer.py --checkpoint .../trial_0001/checkpoint_final.pt --scenario scenarios/drone_ring_lossy_3ring_001 --eval_seeds 0,1,2 --output .../trial_0001/infer_results.json`
- **结果**：`success_rate = 0.667`，`collision_rate = 0.0`，`avg_episode_length = 172.33`
- **结论**：已过 `success_rate >= 0.4` 门槛，但仍需按 `plan.md` 完整 sweep 并寻找更优配置

## 2026-06-28 — Step 5: 首轮 sweep 回归

- **操作**：按 `search_space.yaml` 的 `speed_scale x intercept_gain x safety_margin = 18` 组组合执行完整 sweep
- **问题**：全部可行配置退化为超时主导，最佳 trial 只有 `success_rate = 0.0`
- **定位**：红方对有效观测仍做过度平滑，导致环切换后转向迟滞；不是 train/infer/experiment 目录结构问题
- **处理**：回到 `policy.py`，把观测记忆逻辑改成“仅在丢包时使用记忆，有值时直接采用最新向量”

## 2026-06-28 — Step 6: 策略修正后重跑 sweep

- **复测单点**：旧 `trial_0001` checkpoint 在新策略代码下复测 → `success_rate = 1.0`，`avg_episode_length = 39.0`
- **重跑 18 组 sweep**：全部写回 `experiments/drone_ring_lossy_3ring_exp_001/trials/`
- **最佳结果**：
  - `best_trial`: `trial_0013`
  - `best_config`: `speed_scale=1.4`, `intercept_gain=0.55`, `safety_margin=0.7`, `blue_gate_bias=0.3`, `memory_decay=0.85`, `recovery_gain=1.1`
  - `success_rate = 1.0`
  - `collision_rate = 0.0`
  - `out_of_bounds_rate = 0.0`
  - `avg_episode_length = 35.33`
- **实验 Hook**：`python src/hooks/post_experiment_run.py --exp experiments/drone_ring_lossy_3ring_exp_001` → `passed`
- **freeze_hash**：`1a071fca0f341d669413e594e636e8e27285a5de1ba9c80bf6588a522b54ebf0`

## 2026-06-28 — Step 7: 可视化与最终校验

- **可视化**：使用 `best_config` 重放 seed `0`，输出 `output/example_03_drone_ring_lossy_3ring.png`
- **内容**：2D 轨迹图包含红蓝轨迹、三个圆环、起终点和发生 lossy observation 的步点
- **最终校验**：
  - `python src/hooks/post_scenario_compile.py --scenario scenarios/drone_ring_lossy_3ring_001` → `passed`
  - `python -m pytest scenarios/drone_ring_lossy_3ring_001/tests -q` → `3 passed`
  - `python src/hooks/post_policy_submit.py --policy policies/drone_ring_lossy_3ring_rule_v1` → `passed`
  - `python -m pytest policies/drone_ring_lossy_3ring_rule_v1/tests -q` → `5 passed`
  - `python src/hooks/post_experiment_run.py --exp experiments/drone_ring_lossy_3ring_exp_001` → `passed`
