---
name: game-main
description: 按照 game/<game-id>/plan.md 依次调用三 Codex subagent，完成场景→策略→实验全链路自动科研。
---

# Game Main（自动科研执行）

## 强制规则：每次结束必须生成 Word 报告

每一次 `game-main` 调用结束时，无论最终状态是 `PASS`、`FAIL_STOP`、阶段失败、超时停止，还是断点续跑后的部分完成，都必须在写完 `log.md`、`summary.md` 和可视化产物后生成一份 Word 报告。

- Word 文件：`game/<game-id>/reports/<game-id>_round_report.docx`
- 可复现脚本：`game/<game-id>/reports/build_round_report_docx.py`
- 如果旧报告存在，必须覆盖为当前执行事实；不能保留会误导用户的旧结论。
- 首选 `python-docx` 生成 `.docx`；若不可用，可使用 `docx-js`。不得只生成 Markdown 来替代 Word。
- 生成后必须重新打开 `.docx` 做结构验证：至少检查文件存在且非空、可被 DOCX 解析、段落数、表格数和图片数合理。
- 如果 Word 生成失败，`summary.md` 和最终回复必须显式标记失败原因；不能声称 `game-main` 完整完成。

Word 报告必须包含：
1. 输入任务与场景设定：用户原始场景、agent 数量、布局、出生方式、超时步数、硬约束、空场耦合门禁。
2. 方法概述：策略族、红蓝显式拆分、冻结对手、交替 best response、参数 sweep、受控策略代码迭代上限。
3. 逐轮迭代记录：每一轮的 `round_id`、`target_side`、冻结对手、策略包、实验包、subagent ID、策略改进思路、trial 数、代码修改次数、red/blue utility、target margin、hard constraints、coupling delta、状态。
4. 可视化结果：插入 `game/<game-id>/figures/` 下的 dashboard、trial 分布图、2D/3D 轨迹图；如果某类图不存在，报告中必须说明缺失原因，不能静默跳过。
5. 科研阐述：基于耦合测试、优势方、`best_response_gain_red`、`best_response_gain_blue` 判断博弈是否存在、当前优势方、是否能声称经验近似纳什稳定，以及失败轮的主要原因。
6. 关键产物与验证：列出场景、策略、实验、round history、summary、figures 路径，以及已执行的 hook/pytest 验证命令。

## 概述

读取 `game/<game-id>/plan.md` 中定义的实施计划，按顺序调用三个 Codex subagent（scenario_compiler → policy_designer → experiment_autoresearch），完成从自然语言描述到实验包的全链路自动科研。

## 参数

| 参数 | 必需 | 说明 |
|------|------|------|
| `game-id` | 是 | 任务标识符，对应 `game/<game-id>/` 目录下的 plan.md |
| `--rounds X` | 否 | 三智能体多轮迭代次数，默认 1；第 1 轮执行完整链路，后续轮只重复策略选择和自动科研 |
| `--max-hours H` | 否 | 最大运行小时数（浮点数），默认无限制 |

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
│           空场测试: 当前目标侧 Δ(coupling load)>0            │
│           ↓ (验证通过)                                       │
│  Step 5: 生成 game/<game-id>/summary.md 汇总报告              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

当 `--rounds X > 1` 时：
- 第 1 轮按完整流程执行：scenario_compiler → policy_designer(mode=initial) → experiment_autoresearch(target_side=initial)。
- 根据第 1 轮结果判断劣势方，作为第 2 轮优化目标。
- 第 2..X 轮只重复 policy_designer 与 experiment_autoresearch；每轮在红/蓝之间切换优化目标。
- 必须真实调用 Codex subagent，不得由主 agent 直接伪造 subagent 产物。完整 `--rounds X` 的计划调用数为 `2*X+1`：第 1 轮 3 次（scenario、policy、experiment），后续每轮 2 次（policy、experiment）。如果断点续跑且第 1 轮已完成，则剩余计划调用数为 `2*(X-1)`。
- 第 2..X 轮的产物必须带轮次和目标侧标识，推荐策略包 `<policy_id>_r02_red`、实验包 `<exp_id>_r02_red`；若复用同一策略包，必须维护 `round_history.json` 记录每轮输入、输出和 freeze_hash。
- 场景包始终冻结；每轮必须记录本轮优化方、冻结对手方、策略升级思路、指标变化和是否达标。
- 最后一轮必须输出 2D/3D 可视化和整体报告。

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
- **迭代轮数**：`--rounds X`，未提供时默认为 1

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
如果本轮是 `mode=initial`，且 `policies/<policy_id>/manifest.json` 存在、`freeze_hash` 匹配，并通过 `python src/hooks/post_policy_submit.py --policy policies/<policy_id>` 和 `python -m pytest policies/<policy_id>/tests/` 验证 → **跳过此步骤**，记录到日志。

如果本轮是 `mode=red` 或 `mode=blue`，不能只因基础策略包验证通过就跳过。必须检查本轮 `round_id + target_side` 对应的产物是否已存在并通过验证：推荐路径为 `policies/<policy_id>_rNN_<target_side>/`；若复用同一策略包，则必须在 `round_history.json` 中存在本轮记录、对应 freeze_hash 和验证结果。缺少本轮记录时必须执行 policy_designer。

#### 3.2 执行
调用 `.codex/agents/policy_designer.toml` 定义的 **policy_designer** Codex subagent，输入：
- 冻结的场景包路径：`scenarios/<task_id>/`
- policy_id
- 本轮模式：`initial` / `red` / `blue`

Subagent 的输出目录：`policies/<policy_id>/`

多轮运行时，Subagent 的输出目录应包含轮次和目标侧，推荐 `policies/<policy_id>_rNN_<target_side>/`；若为了兼容旧流程复用 `policies/<policy_id>/`，必须追加或更新 `round_history.json`，不得覆盖丢失前序轮次记录。

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
如果本轮是 `target_side=initial`，且 `experiments/<exp_id>/manifest.json` 存在，并通过 `python src/hooks/post_experiment_run.py --exp experiments/<exp_id>` 验证 → **跳过此步骤**。

如果本轮是 `target_side=red` 或 `target_side=blue`，必须检查本轮 `round_id + target_side` 对应实验包是否已完成：推荐路径为 `experiments/<exp_id>_rNN_<target_side>/`；若复用同一实验包，则必须在 `round_history.json` 中存在本轮记录、对应 policy freeze_hash、实验 freeze_hash、空场测试和达标判断。缺少本轮记录时必须执行 experiment_autoresearch。

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
- 本轮目标侧：`target_side=initial|red|blue`
- （可选）max_trials 限制（从超时预算推算）

Subagent 的输出目录：`experiments/<exp_id>/`

多轮运行时，Subagent 的输出目录应包含轮次和目标侧，推荐 `experiments/<exp_id>_rNN_<target_side>/`；若复用 `experiments/<exp_id>/`，必须追加或更新 `round_history.json`，最终 summary 需要汇总所有轮次，而不是只读取最后一次实验结果。

**关键红线提醒**：
- 场景包始终是冻结的只读黑盒
- 策略包默认按冻结输入处理，优先只通过 config sweep 调参；若参数 sweep 后仍无法满足 primary metric、hard constraints 或空场测试门禁，允许 experiment_autoresearch 进入受控策略代码迭代
- 排名仅用 evaluation_metrics（不用 reward components）
- 每个 trial 必须有 hypothesis
- 自动科研必须持续迭代到本轮目标达标或达到轮次/修改上限，不能只跑一次 sweep 后停止；若本轮未达标，game-main 必须停止后续红蓝交替轮次并在 summary.md 标记未完成，不能把失败轮当作正常完成后继续推进

#### 4.4 验证
```bash
python src/hooks/post_experiment_run.py --exp experiments/<exp_id>
```

#### 4.5 受控策略代码迭代（必要时）
仅当参数 sweep 无法满足晋级门槛时启用。允许 experiment_autoresearch 最小修改当前 `policies/<policy_id>/` 内的 `policy.py`、`default_config.yaml`、`search_space.yaml`、`algorithm_card.md`、`tests/` 和 `manifest.json`。

每次修改策略代码后，必须先回到 Step 3 的策略验证：
```bash
python src/hooks/post_policy_submit.py --policy policies/<policy_id>
python -m pytest policies/<policy_id>/tests/ -v
```

验证通过后才能重新运行实验 sweep。场景包、`src/`、`contracts/`、`hooks/` 仍禁止修改。

#### 4.6 空场测试（博弈存在性门禁）
实验 hook 通过后，必须完成空场测试，不能跳过或仅在 summary.md 中声明。使用同一策略、同一评估配置和同一组 seeds，对当前目标侧做对称验证：
- `target_side=initial` 或 `red`：对比 `U_R(红,∅蓝)` 与 `U_R(红,真蓝)`，计算 `Δ_R(coupling load) = U_R(红,∅蓝) - U_R(红,真蓝)`。
- `target_side=blue`：对比 `U_B(蓝,∅红)` 与 `U_B(蓝,真红)`，计算 `Δ_B(coupling load) = U_B(蓝,∅红) - U_B(蓝,真红)`。

判定标准：当前目标侧 `Δ > 0`。若 `Δ <= 0`，说明对手没有形成有效耦合压力，不能声称博弈存在；必须将结果反馈给 experiment_autoresearch subagent 重试或在 summary.md 中标记实验失败。

#### 4.7 失败处理
- 如果验证失败：将错误信息反馈给 subagent，**最多重试 3 次**
- 如果空场测试失败（`Δ <= 0` 或缺少任一效用值）：按实验验证失败处理，**最多重试 3 次**
- 如果进入策略代码迭代，最多允许 3 轮代码修改；每轮都必须重新通过 policy hook、policy tests、experiment hook 和空场测试
- 3 次重试后仍失败 → 记录失败原因
- 常见失败原因及修正策略：
  - leaderboard.csv 只有 header 无数据 → 要求至少完成 1 个 trial
  - trial 缺少文件 → 要求补充缺失的 metrics.json/log.json
  - 排名错误 → 检查 ranking_key 逻辑
  - 空场测试 `Δ <= 0` → 检查真实蓝方是否参与评估、奖励耦合项是否生效、空场与真蓝条件是否使用相同 seeds

#### 4.8 日志
记录：时间戳、round_id、target_side、exp_id、trial 总数、best config、主要指标、是否进入策略代码迭代、policy freeze_hash（如有变化）、验证结果、当前目标侧空场测试的 `U_side(side,∅opponent)`、`U_side(side,真opponent)`、`Δ(coupling load)`、耗时。

---

### Step 4.9: 多轮红蓝交替迭代
当 `--rounds X > 1` 时执行：
1. Round 1 使用 `mode=initial` / `target_side=initial`，产出 baseline。
2. 从 baseline 判断劣势方：若 `red_utility - blue_utility < 0`，下一轮优化红方；若 `> 0`，下一轮优化蓝方；若等于 0，按 plan.md 中指定优先方，否则默认红方。
3. Round 2..X 交替切换 `red` / `blue`，每轮只允许优化当前方，另一方冻结。
4. 每轮产物必须带 `round_id + target_side`，推荐 `policies/<policy_id>_rNN_<target_side>/` 和 `experiments/<exp_id>_rNN_<target_side>/`；若复用目录，必须用 `round_history.json` 保留每轮记录。
5. 每轮结束必须记录 `advantage_score`、本轮 `best_response_gain_side`、采取的策略升级思路、是否改变策略代码、是否达标。
6. 任一 `experiment_autoresearch` 轮未达标时立即停止后续轮次，记录达到的上限和失败原因；只有全部轮次达标后，最后一轮报告才可分析优势方和经验近似纳什稳定性。纳什近似判断必须同时引用最近一次红方 `best_response_gain_red` 和最近一次蓝方 `best_response_gain_blue`。

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
- **Utility 来源**：说明 `red_utility` / `blue_utility` 来自 `optimization_target.utility_definition`、`red_score/blue_score`，还是跨 seed 平均累计 reward
- **空场测试**：按目标侧记录 `U_side(side,∅opponent)=<value>`, `U_side(side,真opponent)=<value>`, `Δ(coupling load)=<value>`，判定：通过（`Δ > 0`）/ 失败
- **多轮迭代记录**：列出每轮 `round_id`、`target_side`、策略包路径、实验包路径、冻结对手方、策略升级思路、`advantage_score`、`best_response_gain_side`
- **终局博弈分析**：基于 `advantage_score`、最近一次 `best_response_gain_red` 和最近一次 `best_response_gain_blue` 判断优势方与经验近似纳什稳定性
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
- [x] 如果 experiment_autoresearch 修改过策略代码，已重新通过 policy hook、policy tests，并更新 policy manifest/freeze_hash
- [x] 最终实验已完成当前目标侧的对称空场测试，且 `Δ(coupling load)>0`
- [x] 未完成阶段在 summary.md 中有明确的失败原因说明
- [x] 所有冻结产物（scenarios、policies、experiments）的 manifest.json 包含正确的 freeze_hash
