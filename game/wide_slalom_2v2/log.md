# wide_slalom_2v2 执行日志

## 2026-06-10 — Step 1: 初始化

- **输入**：`game/wide_slalom_2v2/plan.md`
- **最大运行时间**：2 小时
- **task_id**：`wide_slalom_2v2_001`
- **policy_id**：`wide_slalom_2v2_rule_v1`
- **exp_id**：`wide_slalom_2v2_exp_001`
- **断点检查**：场景、策略、实验产物均未完成
- **验证结果**：继续执行

## 2026-06-10 — Step 2: 场景编译

- **输入**：红方 2 机（racer + defender escort）对蓝方 2 机（racer + defender intercept），`wide_slalom`，600 步
- **输出路径**：`scenarios/wide_slalom_2v2_001/`
- **freeze_hash**：`sha256:9d80edf247600a9ae9183a9a42e0c888a0eab68ffcf50b152a804c4de6289c7b`
- **验证结果**：通过，`python src/hooks/post_scenario_compile.py --scenario scenarios/wide_slalom_2v2_001`
- **重试次数**：0
- **折中说明**：场景 spec/config 显式记录 2v2 角色和 `wide_slalom`，env API 使用 32 维固定观测、4 维动作；动作后两维保留兼容

## 2026-06-10 — Step 3: 策略设计

- **输入**：`scenarios/wide_slalom_2v2_001/`
- **输出路径**：`policies/wide_slalom_2v2_rule_v1/`
- **freeze_hash**：`sha256:b4fc694df6213eac6856641b7d9685cb7b506e54a55707b34c97f2fe05c7d3ba`
- **验证结果**：通过，`python src/hooks/post_policy_submit.py --policy policies/wide_slalom_2v2_rule_v1`；包内测试 `4 passed`
- **重试次数**：0
- **折中说明**：策略按 agent role 做规则分派，但受 12 维观测限制，护航与拦截为 M1 近似语义

## 2026-06-10 — Step 4: 实验运行

- **输入**：`scenarios/wide_slalom_2v2_001/` + `policies/wide_slalom_2v2_rule_v1/`
- **输出路径**：`experiments/wide_slalom_2v2_exp_001/`
- **freeze_hash**：`sha256:b68b966ce10b16648518c12d15aff7a5e0f879847b59f94f5f47696c5e10fc97`
- **验证结果**：通过，`python src/hooks/post_experiment_run.py --exp experiments/wide_slalom_2v2_exp_001`
- **重试次数**：0
- **trial 数量**：9
- **best trial**：`trial_0007`
- **best primary metric**：`success_rate = 1.0`
- **硬约束结果**：best trial 通过，`collision_rate = 0.0`，`out_of_bounds_rate = 0.0`，`action_violation_rate = 0.0`
- **折中说明**：策略搜索空间主要使用 `min/max/default`，实验阶段执行 priority_1 的确定性 3x3 网格 sweep

## 2026-06-10 — Step 5: 需求迭代

- **问题定位**：旧策略中蓝方赛车机阻断规则朝红方靠近，导致中段门附近硬碰撞；旧 `infer.py` 还是 smoke stub，固定输出 `success_rate=0`
- **修正内容**：蓝方赛车机改为带横向 lane offset 的保守竞速/阻断，并强化近距离避让；`infer.py` 改为真实加载场景环境并按 eval seeds rollout
- **策略 freeze_hash**：`sha256:b4fc694df6213eac6856641b7d9685cb7b506e54a55707b34c97f2fe05c7d3ba`
- **验证结果**：场景 hook 通过；策略 hook 通过；策略包测试 `4 passed`；实验 hook 通过
- **当前 best trial**：`trial_0007`，`success_rate=1.0`，所有 hard constraints 通过，decision=`promote`

## 2026-06-10 — Step 6: 32 维观测对齐

- **问题定位**：计划要求观测包含队友、双敌、门状态和角色信息；早期 12 维观测只保留了 M1 兼容最小状态
- **修正内容**：场景 `observation_space.shape` 扩展为 `[32]`；`env.py` 返回队友相对状态、两个敌方相对状态、下一门方向/距离、角色 one-hot、最近敌方状态、门索引和归一化步数
- **兼容处理**：策略解析同时支持 32 维真实场景观测和 12 维 hook/test smoke 观测
- **场景 freeze_hash**：`sha256:9d80edf247600a9ae9183a9a42e0c888a0eab68ffcf50b152a804c4de6289c7b`
- **策略 freeze_hash**：`sha256:b4fc694df6213eac6856641b7d9685cb7b506e54a55707b34c97f2fe05c7d3ba`
- **实验 freeze_hash**：`sha256:b68b966ce10b16648518c12d15aff7a5e0f879847b59f94f5f47696c5e10fc97`
- **验证结果**：场景 hook 通过；场景包测试 `3 passed`；策略 hook 通过；策略包测试 `5 passed`；实验 hook 通过
