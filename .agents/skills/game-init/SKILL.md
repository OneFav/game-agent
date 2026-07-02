---
name: game-init
description: 根据用户描述的博弈场景与智能体角色，结合现有代码和规范，生成 game/<game-id>/plan.md 初步实施计划。
---

# Game Init（项目初始化）

## 概述

当用户提供以下信息时使用此技能生成项目计划：
1. **场景描述**：自然语言描述的博弈场景（如"红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 60 步"）
2. **智能体角色描述**：各方角色的目标、约束和能力（可选）

此技能会读取项目现有的代码能力和接口规范，分析需求，然后生成 `game/<game-id>/plan.md` — 一份包含完整实施计划的文档。

## 工作流程

### Step 1: 读取项目上下文

在分析用户需求前，先全面理解当前系统能力。读取以下文件：

**架构与总览**：
- `CLAUDE.md` — 项目架构总览、三 Agent 流水线、模块索引
- `README.md` — 快速开始和 CLI 用法

**接口合同（定义数据格式和交互协议）**：
- `INTERFACE_1_SCENARIO_TO_POLICY.md` — 场景包的完整 schema，供策略设计和实验消费
- `INTERFACE_2_POLICY_TO_AUTORESEARCH.md` — 策略包的完整 schema，供实验消费

**合约定义（不可变的协议层）**：
- `src/contracts/policy_protocol.py` — Policy ABC 定义（所有策略必须实现的接口）
- `src/contracts/scenario_schema.yaml` — 场景包 schema 定义（task_family 枚举、必需字段等）

**参考实现（代码能力边界）**：
- `src/game_agent/scenario_compiler/compiler.py` — 场景编译器实现（理解解析能力和模板）
- `src/game_agent/policy_designer/designer.py` — 策略设计器实现（理解策略生成逻辑）
- `src/game_agent/autoresearch/runner.py` — 实验运行器实现（理解 sweep 和排名逻辑）
- `src/game_agent/envs/drone_ring_game/env.py` — 环境参考实现（理解状态/动作空间定义）

**Codex Subagent 定义**：
- `.codex/agents/scenario_compiler.toml` — 场景编译 subagent 的能力和边界
- `.codex/agents/policy_designer.toml` — 策略设计 subagent 的能力和边界
- `.codex/agents/experiment_autoresearch.toml` — 实验运行 subagent 的能力和边界

### Step 2: 分析用户需求

根据用户的场景描述和人物描述，进行形式化分析：

#### 2.1 任务族判断
- 当前系统支持的任务族：`drone_ring_game`（红方过环，蓝方拦截）
- 如果用户的描述属于 drone_ring_game 变体 → 标记为现有任务族
- 如果描述涉及新博弈类型 → 标记为需要扩展现有系统，在风险部分注明

#### 2.2 参数抽取
从自然语言描述中抽取：
- **圆环数量**：支持中文数字（一/二/两/三/四/五）和阿拉伯数字
- **超时步数**：描述中的超时或最大步数
- **通信模式**：
  - `perfect` — 无延迟无丢包
  - `delayed` — 有通信延迟（需要延迟步数）
  - `lossy` — 有丢包（需要丢包概率）
- **formalism**：
  - 出现"对抗、追击、拦截、红蓝、局部"关键词 → `POSG`
  - 仅单方决策 → `MDP`
  - 双方同时决策无局部观测 → `MarkovGame`
- **硬约束**：碰撞率、出界率、动作违规率等
- **中性观测指标**：红方得分、蓝方得分、碰撞率、出界率、动作违规率、平均完成时间等；不要在场景建模阶段决定红/蓝某一方的最终成功阈值

#### 2.3 角色分析
- **红方目标**：穿过圆环，最小化被拦截次数
- **蓝方目标**：拦截红方，预测红方路径
- **约束条件**：速度限制、视野范围、通信条件
- **奖励耦合要求**：如果需求属于对抗博弈任务（如 `POSG`、`MarkovGame`、红蓝对抗、追击拦截），红蓝双方的奖励函数不得彼此独立。`reward_structure` 必须体现双方行为的相互影响：红方效用受真实蓝方拦截压力影响，蓝方效用受红方推进、逃逸或完成任务影响。不要把红蓝奖励写成两个互不引用对方状态或结果的单智能体目标。

### Step 3: 生成 plan.md

输出 `game/<game-id>/plan.md`，必须包含以下章节：

```markdown
# <game-id> 实施计划

## 一、需求分析
- **任务族**：drone_ring_game / 新任务族
- **场景描述摘要**：用一两句话概括用户场景
- **形式化定义**：formalism、角色、目标函数
- **奖励耦合说明**：若为对抗博弈，明确红蓝奖励如何相互耦合；若非对抗任务，说明为何可独立建模
- **指标职责说明**：场景包只提供中性观测指标和硬约束；红/蓝某一方的成功指标由策略包在 `mode=initial|red|blue` 中定义
- **关键参数表**：列出所有已抽取的参数和取值

## 二、场景包设计
- **task_spec.yaml 设计要点**：
  - task_family、formalism 确定
  - observation_space 设计（维度、范围）
  - action_space 设计（维度、范围）
  - reward_structure 设计（各 reward component 的定义和权重；对抗任务必须包含红蓝耦合项，避免双方奖励彼此独立）
  - evaluation_metrics 设计（中性观测指标、secondary、hard_constraints；不写死红/蓝优势阈值）
  - termination_conditions（最大步数、任务完成条件）
- **env.py 需求**：
  - 环境动力学描述
  - 需要自定义的行为（如有）
  - 测试需求（确定性、形状正确性）
- **assumptions.md 要点**：列出所有未在描述中明确的默认值

## 三、策略包设计
- **推荐算法族**：规则策略 / MPC / PPO / MAPPO / 混合
- **策略选择模式**：`initial` / `red` / `blue`，其中 `red` 只优化红方，`blue` 只优化蓝方
- **成功指标定义**：由策略选择智能体根据当前模式定义，默认优势阈值为 `0.0`
- **选择理由**：为什么推荐这个算法
- **策略架构**：
  - 输入/输出接口
  - 动作裁剪策略
  - safety_gate 设计（如有特殊需求）
- **搜索空间建议**：
  - priority_1 参数（核心调优）
  - priority_2 参数（次要调优）
  - do_not_tune 参数（固定）

## 四、实验方案设计
- **搜索空间大小**：笛卡尔积估计
- **推荐 trial 数量**（默认：18）
- **seeds 数量**（每个 trial 至少 3 个 seed）
- **预算估计**：基于单 trial 平均耗时
- **晋级标准**：success_rate 提升阈值、稳定性阈值

## 五、交接说明
- **Agent 1 → Agent 2**：场景包的关键接口点（action_space、observation_space、reward_structure vs evaluation_metrics 的区别）
- **Agent 2 → Agent 3**：策略包的关键接口点（train.py CLI 签名、search_space.yaml、get_config_schema() 一致性）
- **跨阶段约束**：冻结策略（freeze_hash）、不可修改的字段

## 六、预期产出
- **scenarios/<task_id>/** 的文件列表和关键内容摘要
- **policies/<policy_id>/** 的文件列表和关键内容摘要
- **experiments/<exp_id>/** 的文件列表和预期指标

## 七、风险与未知
- **需要进一步明确的问题**（如用户的描述中有歧义）
- **当前系统不支持的功能**（如新任务族需要的环境修改）
- **预期失败模式和应对策略**
```

### Step 4: 验证计划

生成 plan.md 后，确认：
- [x] 所有从用户描述中能确定的参数都已列出
- [x] 所有默认值都有理由说明
- [x] task_id / policy_id / exp_id 已推导或使用默认命名规则
- [x] 如果涉及新任务族，已在风险章节标注
- [x] plan.md 的大小至少 500 字（确保足够详细）

## 注意事项

1. **当前系统边界**：
   - 仅支持 `drone_ring_game` 任务族
   - M1 聚焦规则策略和轻量实验（不涉及大规模 RL 训练）
   - 不涉及真实无人机仿真

2. **命名约定**：
   - task_id：`<game-id>_001`（或用户指定）
   - policy_id：`<game-id>_rule_v1`（规则策略）或 `<game-id>_<algo>_v1`（其他算法）
   - exp_id：`<game-id>_exp_001`

3. **plan.md 是一份活文档**：
   - 由 `game-main` 在执行过程中读取和参考
   - 可以在遇到阻塞时回过来修改 plan.md
   - 不是一成不变的合同，而是指导性路线图
