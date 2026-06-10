---
name: game-main
description: 按照 game/<game-id>/plan.md 依次调用三 Codex subagent，完成场景→策略→实验全链路自动科研。
---

# Game Main（自动科研执行）

## 概述

读取 `game/<game-id>/plan.md` 中定义的实施计划，按顺序调用三个 Codex subagent（scenario_compiler → policy_designer → experiment_autoresearch），完成从自然语言描述到实验包的全链路自动科研。

## 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `game-id` | 是 | 任务标识符，对应 `game/<game-id>/` 目录下的 plan.md |
| `--max-hours X` | 否 | 最大运行小时数（浮点数），默认无限制 |

## 前置条件

执行此技能前必须满足：
1. ✅ `game/<game-id>/plan.md` 已通过 `game-init` 技能生成
2. ✅ Python 环境已就绪：`pip install -e ".[dev]"` 安装完成
3. ✅ 三个 Codex subagent 的 TOML 定义存在于 `.codex/agents/`
4. ✅ `game/<game-id>/` 目录存在且可写入

## 完整工作流程

```
┌──────────────────────────────────────────────────────────────┐
│                   Game Main 执行流程                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: 读取 plan.md，确定 task_id / policy_id / exp_id     │
│           ↓                                                  │
│  Step 2: 调用 scenario_compiler subagent                    │
│           验证: python src/hooks/post_scenario_compile.py    │
│           ↓ (验证通过)                                       │
│  Step 3: 调用 policy_designer subagent                      │
│           验证: python src/hooks/post_policy_submit.py       │
│           ↓ (验证通过)                                       │
│  Step 4: 调用 experiment_autoresearch subagent              │
│           验证: python src/hooks/post_experiment_run.py      │
│           ↓ (验证通过)                                       │
│  Step 5: 生成 game/<game-id>/summary.md 汇总报告              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### Step 1: 读取计划并确定参数

#### 1.1 读取 plan.md
读取 `game/<game-id>/plan.md`，提取以下信息：
- **task_id**：场景包标识符。如果 plan.md 中未指定，默认使用 `<game-id>_001`
- **policy_id**：策略包标识符。如果未指定，默认使用 `<game-id>_rule_v1`
- **exp_id**：实验包标识符。如果未指定，默认使用 `<game-id>_exp_001`
- **场景参数**：圆环数量、通信模式、超时步数、formalism
- **策略建议**：推荐算法族、搜索空间、action bounds 约束
- **实验预算**：推荐 trial 数、seeds 数量

#### 1.2 构建 task 自然语言描述
从 plan.md 的"需求分析"章节和"场景包设计"章节，构造完整的自然语言 task_text。
这将成为 scenario_compiler subagent 的输入。

#### 1.3 初始化日志
在 `game/<game-id>/log.md` 创建执行日志，记录开始时间。

---

### Step 2: 调用场景编译 Subagent

#### 2.1 检查是否已完成
如果 `scenarios/<task_id>/manifest.json` 存在且 `freeze_hash` 匹配（通过 `python src/hooks/post_scenario_compile.py --scenario scenarios/<task_id>` 验证通过）→ **跳过此步骤**，记录到日志。

#### 2.2 执行
调用 `.codex/agents/scenario_compiler.toml` 定义的 **scenario_compiler** Codex subagent，输入：
- 自然语言任务描述（从 plan.md 构造）
- task_id

Subagent 的输出目录：`scenarios/<task_id>/`

#### 2.3 验证
```bash
python src/hooks/post_scenario_compile.py --scenario scenarios/<task_id>
```

#### 2.4 失败处理
- 如果验证失败（退出码非 0）：将错误信息反馈给 subagent，**最多重试 3 次**
- 3 次重试后仍失败 → 记录失败原因到 log.md，**停止后续所有步骤**，生成 summary.md 标记失败状态
- 常见失败原因及修正策略：
  - task_spec.yaml 缺少必需字段 → 要求 subagent 重新检查 schema
  - assumptions.md 为空 → 要求补充默认值说明
  - env.py 非确定性 → 要求移除所有非受控随机源

#### 2.5 日志
记录：时间戳、task_id、生成的 freeze_hash、验证结果（通过/失败）、耗时。

---

### Step 3: 调用策略设计 Subagent

#### 3.1 检查是否已完成
如果 `policies/<policy_id>/manifest.json` 存在且 `freeze_hash` 匹配（通过 `python src/hooks/post_policy_submit.py --policy policies/<policy_id>` 和 `python -m pytest policies/<policy_id>/tests/` 验证通过）→ **跳过此步骤**，记录到日志。

#### 3.2 执行
调用 `.codex/agents/policy_designer.toml` 定义的 **policy_designer** Codex subagent，输入：
- 冻结的场景包路径：`scenarios/<task_id>/`
- policy_id

Subagent 的输出目录：`policies/<policy_id>/`

**重要**：场景包是冻结的只读输入。确保 subagent 不会修改 scenarios/ 下的任何文件。

#### 3.3 验证
```bash
# 第一步：Hook 验证
python src/hooks/post_policy_submit.py --policy policies/<policy_id>

# 第二步：包内测试
python -m pytest policies/<policy_id>/tests/ -v
```

#### 3.4 失败处理
- 如果验证失败：将错误信息反馈给 subagent，**最多重试 3 次**
- 3 次重试后仍失败 → 记录失败原因，停止后续步骤
- 常见失败原因及修正策略：
  - PolicyClass 未继承 Policy ABC → 要求 subagent 实现 `from contracts.policy_protocol import Policy`
  - search_space.yaml 参数不在 get_config_schema() 中 → 要求对齐
  - act() 输出越界 → 要求添加 np.clip()

#### 3.5 日志
记录：时间戳、policy_id、生成的 freeze_hash、验证结果、耗时。

---

### Step 4: 调用实验 Subagent

#### 4.1 检查是否已完成
如果 `experiments/<exp_id>/manifest.json` 存在（通过 `python src/hooks/post_experiment_run.py --exp experiments/<exp_id>` 验证通过）→ **跳过此步骤**。

#### 4.2 超时检查
- 如果设置了 `--max-hours X`，在开始前检查已用时间
- 如果剩余时间 < 10 分钟：跳过此步骤，summary.md 中标注"实验阶段因超时跳过"
- 如果剩余时间足够但有限：根据剩余时间缩减实验预算：
  - 减少 `max_trials`
  - 减少 `seeds_per_trial`
  - 只调优 `priority_1` 参数

#### 4.3 执行
调用 `.codex/agents/experiment_autoresearch.toml` 定义的 **experiment_autoresearch** Codex subagent，输入：
- 冻结的场景包路径：`scenarios/<task_id>/`
- 冻结的策略包路径：`policies/<policy_id>/`
- exp_id
- （可选）max_trials 限制（从超时预算推算）

Subagent 的输出目录：`experiments/<exp_id>/`

**关键红线提醒**：
- 场景和策略包均为冻结的只读黑盒
- 排名仅用 evaluation_metrics（不用 reward components）
- 每个 trial 必须有 hypothesis

#### 4.4 验证
```bash
python src/hooks/post_experiment_run.py --exp experiments/<exp_id>
```

#### 4.5 失败处理
- 如果验证失败：将错误信息反馈给 subagent，**最多重试 3 次**
- 3 次重试后仍失败 → 记录失败原因
- 常见失败原因及修正策略：
  - leaderboard.csv 只有 header 无数据 → 要求至少完成 1 个 trial
  - trial 缺少文件 → 要求补充缺失的 metrics.json/log.json
  - 排名错误 → 检查 ranking_key 逻辑

#### 4.6 日志
记录：时间戳、exp_id、trial 总数、best config、主要指标、验证结果、耗时。

---

### Step 5: 生成汇总报告

在 `game/<game-id>/summary.md` 写入最终报告。

#### summary.md 模板

```markdown
# <game-id> 执行汇总

**执行时间**：<开始时间> ~ <结束时间>（总共 <N> 分钟）

## 各阶段状态

| 阶段 | 状态 | 耗时 | 产物路径 |
|------|------|------|----------|
| 场景编译 | ✅ 成功 / ⚠️ 跳过 / ❌ 失败 | <time> | `scenarios/<task_id>/` |
| 策略设计 | ✅ 成功 / ⚠️ 跳过 / ❌ 失败 | <time> | `policies/<policy_id>/` |
| 实验运行 | ✅ 成功 / ⚠️ 跳过 / ❌ 失败 | <time> | `experiments/<exp_id>/` |

## 场景包

- **路径**：`scenarios/<task_id>/`
- **freeze_hash**：`<hash>`
- **关键参数**：圆环数量=<N>, 通信模式=<mode>, 超时步数=<N>, formalism=<type>

## 策略包

- **路径**：`policies/<policy_id>/`
- **freeze_hash**：`<hash>`
- **算法**：<算法族>
- **PolicyClass**：<类名>

## 实验包

- **路径**：`experiments/<exp_id>/`
- **Trial 总数**：<N>
- **Best Config**：<config 摘要>
- **Primary Metric**：<名称> = <值>
- **Leaderboard Top 3**：
  1. <trial_id>: <metric> = <value>
  2. <trial_id>: <metric> = <value>
  3. <trial_id>: <metric> = <value>

## 遗留问题

（如果有未完成的阶段，在此说明原因和剩余工作量）
```

---

## 超时控制

### 机制
- 在每个 Step 开始前检查已用时间（当前时间 - 开始时间）
- 已用时间记录在 `game/<game-id>/log.md` 中

### 判断逻辑
```
已用时间 = now - start_time
剩余时间 = max_hours * 3600 - 已用时间

if 剩余时间 < 600:  # 10 分钟
    跳过当前及后续所有步骤
elif 剩余时间 < 估计的单步时间:
    缩减预算（减少 trials/seeds）
    继续执行
else:
    正常执行
```

### 超时后的 summary.md
- 标注各阶段完成状态（✅/⚠️/❌）
- 未完成阶段说明原因："因超时跳过（已用 X 小时，设定最大 Y 小时）"
- 已完成阶段的产物路径和 freeze_hash 仍然保留（可用于断点续跑）

---

## 错误恢复

### 中断恢复
如果 game-main 执行中断（手动停止或超时），再次运行时会自动检测已完成的阶段：
- 检测是否已完成 → 通过 `manifest.json` 中的 `freeze_hash` + hook 验证
- 已完成的阶段自动跳过，从中断点继续
- 这是**断点续跑**机制，不需要从头开始

### 阶段失败处理
- 每个阶段最多**重试 3 次**
- 重试时有针对性地修改输入（将验证错误信息作为修正需求反馈给 subagent）
- 3 次重试后仍失败 → 不继续后续阶段，直接跳到 Step 5 生成 summary.md
- 单个阶段失败**不会回滚**之前已成功的阶段产物

### 日志位置
所有日志写入 `game/<game-id>/log.md`，格式：
```markdown
## <时间戳> — Step N: <阶段名称>

- **输入**：<关键输入参数>
- **输出路径**：<产物目录>
- **freeze_hash**：<hash>
- **验证结果**：✅ 通过 / ❌ 失败（错误信息）
- **重试次数**：<N>
- **耗时**：<time>
```

## 验证清单

在声明 game-main 完成前，确认：

- [x] `game/<game-id>/log.md` 包含每个阶段的完整记录
- [x] `game/<game-id>/summary.md` 包含所有完成阶段的产物路径和 freeze_hash
- [x] 所有已完成阶段的 hook 验证全部通过（退出码 0）
- [x] 未完成阶段在 summary.md 中有明确的失败原因说明
- [x] 所有冻结产物（scenarios、policies、experiments）的 manifest.json 包含正确的 freeze_hash
