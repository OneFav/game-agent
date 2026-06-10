# wide_slalom_2v2 执行汇总

**执行时间**：2026-06-10  
**最大运行时间**：2 小时

## 各阶段状态

| 阶段 | 状态 | 产物路径 |
|------|------|----------|
| 场景编译 | 成功 | `scenarios/wide_slalom_2v2_001/` |
| 策略设计 | 成功 | `policies/wide_slalom_2v2_rule_v1/` |
| 实验运行 | 成功，存在可晋级配置 | `experiments/wide_slalom_2v2_exp_001/` |

## 场景包

- **路径**：`scenarios/wide_slalom_2v2_001/`
- **freeze_hash**：`sha256:9d80edf247600a9ae9183a9a42e0c888a0eab68ffcf50b152a804c4de6289c7b`
- **关键参数**：红方 2 机、蓝方 2 机，`gate_layout=wide_slalom`，`max_steps=600`，`communication.mode=perfect`，`formalism=POSG`
- **验证**：`python src/hooks/post_scenario_compile.py --scenario scenarios/wide_slalom_2v2_001` 通过
- **观测/动作**：每个 agent 使用 32 维固定观测，包含自身、队友、两名敌方、门状态和角色信息；动作保持 4 维，其中前两维为 2D 速度命令，后两维保留兼容。

## 策略包

- **路径**：`policies/wide_slalom_2v2_rule_v1/`
- **freeze_hash**：`sha256:b4fc694df6213eac6856641b7d9685cb7b506e54a55707b34c97f2fe05c7d3ba`
- **算法**：规则策略
- **PolicyClass**：`PolicyClass`
- **验证**：`python src/hooks/post_policy_submit.py --policy policies/wide_slalom_2v2_rule_v1` 通过；包内测试 `5 passed`
- **折中**：由于观测不含完整队友状态和全局门序列，护航、拦截和阻断行为是 M1 兼容近似；蓝方赛车机使用横向 lane offset 和近距离避让，避免通过硬碰撞阻断。

## 实验包

- **路径**：`experiments/wide_slalom_2v2_exp_001/`
- **freeze_hash**：`sha256:b68b966ce10b16648518c12d15aff7a5e0f879847b59f94f5f47696c5e10fc97`
- **Trial 总数**：9
- **Best trial**：`trial_0007`
- **Best Config**：`racer_gain=1.0`，`intercept_gain=0.75`，其余参数保持默认
- **Primary Metric**：`success_rate = 1.0`
- **硬约束**：best trial 通过，`collision_rate = 0.0`，`out_of_bounds_rate = 0.0`，`action_violation_rate = 0.0`
- **Leaderboard Top 3**：
  1. `trial_0007`: `success_rate = 1.0`, `collision_rate = 0.0`, `decision = promote`
  2. `trial_0005`: `success_rate = 1.0`, `collision_rate = 0.0`, `decision = promote`
  3. `trial_0006`: `success_rate = 1.0`, `collision_rate = 0.0`, `decision = promote`
- **验证**：`python src/hooks/post_experiment_run.py --exp experiments/wide_slalom_2v2_exp_001` 通过

## 遗留问题

- 当前实现仍是 M1 兼容的 2D 自包含环境，未完全切换到 `swarm_combat` 3D wrapper。
- 当前 search space 主要使用 `min/max/default`，实验阶段已按 priority_1 生成确定性网格；后续可把 priority_1 参数改成显式 `values`，让主 runner 无需折中即可展开。
