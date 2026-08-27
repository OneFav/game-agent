# AutoGame 实验工作台产品方案 V2

> 状态：待评审
> 本版取代 V1 的“固定三页面、只读结果浏览器”产品骨架。
> 核心变化：项目会话管理 + 动态流程工作区 + 统一人机交互区。
> 微调原则：流程默认自主推进，人拥有随时干预权；Suite 中每个场景分别进入历史项目。

## 1. 产品定义

AutoGame 是一个以项目会话为单位的实验工作台。

它的使用方式接近 Chat Agent：用户新建一个项目，Agent 默认自主推进研究；项目的目标、方法选择、执行过程、实验结果、人工干预和产物都保留在同一个项目会话中。用户可以随时从左侧历史项目返回此前工作，而不是从文件目录重新寻找上下文。

工作台同时解决三件事：

1. 记录一个实验项目从目标到结果的完整上下文；
2. 让用户随时知道当前位于什么流程、已经发生了什么、得到了什么结果；
3. 让 Agent 根据具体任务选择最合适的呈现和交互方式。

产品不是一个固定 Dashboard，也不是只把已有 JSON 字段机械地搬到页面上。稳定的是产品外壳和数据可信边界；变化的是流程结构、信息组织、图表、方法说明和可操作项。

## 2. 核心界面骨架

```text
┌──────────────────────┬──────────────────────────────────────────────┐
│  + 新建项目           │  项目标题 / 当前目标 / 项目级操作             │
│                      ├──────────────────────────────────────────────┤
│  历史项目             │                                              │
│  ├─ S01 交叉碰撞密集区 │  当前流程位置                                │
│  ├─ S02 高速迎面交汇   │  ○ 定义问题 ─ ● 选择方法 ─ ○ 运行 ─ ○ 评估   │
│  ├─ S47 五十智能体集群 │                                              │
│  └─ 3v3 波浪赛优化     │  当前流程的信息、实验内容与结果               │
│                      │  ┌───────────┬───────────┬──────────────┐    │
│  搜索 / 归档          │  │ 方法选择   │ 回放/视频  │ 图表/比较     │    │
│                      │  └───────────┴───────────┴──────────────┘    │
│                      │                                              │
│                      ├──────────────────────────────────────────────┤
│                      │  人机交互区                                   │
│                      │  当前采用 PPO  [改用 SAC] [调整搜索空间]       │
│                      │  对话输入、参数、暂停、覆盖、停止、重试、导出    │
└──────────────────────┴──────────────────────────────────────────────┘
```

页面分为三块：

- 左侧：项目会话历史；
- 右侧上方：流程与实验内容；
- 右侧下方：当前上下文中人可以执行的所有交互。

这三个区域固定存在，但各区域内部的内容可以动态变化。

## 3. 左侧：项目会话管理

### 3.1 新建项目

进入产品后默认可以新建项目。新项目首先只需要一个目标输入，不要求用户预先理解 scenario、policy、experiment 或 suite 的目录结构。

示例：

- “测试 50 类无人机场景，找出策略薄弱点”；
- “为两步通信延迟场景选择并训练一个策略”；
- “继续优化 vertical_wave_3v3 的红方策略”；
- “比较 PPO、SAC 和规则策略的表现”。

Agent 根据目标声明初始流程，并自主选择可以直接执行的方法。方法、理由和替代项保持可见，用户可以介入修改，但不需要点击确认来推动普通流程。

### 3.2 历史项目

左侧项目列表类似会话列表，显示必要信息：

- 项目名称；
- 最近更新时间；
- 当前流程名称；
- 只有异常、暂停或值得关注时才出现提醒标记。

不在列表中显示完整进度、指标或 Agent 活动摘要。

支持：

- 搜索；
- 重命名；
- 置顶；
- 归档；
- 从现有 game、scenario 或 experiment 导入为项目；
- 导入 suite run 时，为其中每个 scenario 分别创建或更新一个历史项目；
- 新建项目时引用历史项目作为 baseline。

Suite 在左侧可以作为折叠分组、搜索条件或批量操作来源，但不是一个代替 50 个场景的单独历史项目。导入 50 场景 suite 后，用户获得 50 个可分别继续、比较和干预的项目会话。

### 3.3 项目与仓库产物的关系

一个工作台项目以一个明确研究对象为中心，并可以关联它产生的多个仓库产物。对于 50 场景 suite，每个项目以一个 scenario 为中心：

```text
Workbench Project
├── scenario_id: S47
├── suite_run: max_space_50_v1_...
├── scenarios/S47
├── baseline replay / metrics
├── candidate replay / metrics
└── comparison / decision evidence
```

项目不是新的实验产物层级，而是把现有产物组织成一个持续会话。

## 4. 右侧上方：流程与实验内容

### 4.1 流程不是固定步骤

产品不预设所有项目都必须经过相同的三步或五步。Agent 可以根据任务声明流程。

例如，训练项目可能是：

```text
定义目标 → 构造环境 → 选择算法 → 训练 → 评估 → 对比
```

规则策略项目可能是：

```text
定义目标 → 选择控制方法 → 参数搜索 → 回放验证
```

由 suite 批量创建的单场景项目可能是：

```text
读取场景 → 运行 baseline → 运行 candidate → 约束检查 → 差异分析
```

交替最佳响应项目可能是：

```text
选择目标方 → 冻结对手 → 生成 trial → 晋级检查 → 下一轮
```

### 4.2 流程位置

流程区始终回答三个问题：

- 当前在哪个流程节点？
- 该节点已经产生了什么？
- 人现在可以在哪里介入、暂停或改变后续？

流程节点仅使用少量通用状态：

- `pending`：尚未开始；
- `active`：正在执行；
- `complete`：已产生所需结果；
- `paused`：被用户暂停；
- `blocked`：执行失败或约束阻止继续。

“可干预”是一项能力，不是阻塞流程的状态。Agent 不反复手工更新节点状态；状态由追加式项目事件推导，例如节点进入、命令完成、artifact 产生、约束失败、用户暂停或用户覆盖选择。

### 4.3 当前节点内容

流程下方显示当前节点最需要的信息。它不是固定卡片集合，而是由 Agent 选择的“呈现块”组成。

可用呈现块包括：

| 类型 | 适用内容 |
|---|---|
| `method-choice` | 算法、控制器、数据处理方法选择 |
| `method-card` | 当前采用的方法、理由和关键限制 |
| `parameter-space` | 可调参数、冻结参数和搜索空间 |
| `spatial-replay` | 2D/3D 回放、轨迹、目标和关系 |
| `video` | 实验视频或导出的 replay |
| `time-series` | reward、loss、primary metric、约束指标 |
| `distribution` | 多 seed、trial 或 round 分布 |
| `comparison` | baseline/candidate、算法或处理方法对比 |
| `table` | leaderboard、trial、scenario 结果 |
| `event-timeline` | 碰撞、通信、通过、终止等事件 |
| `artifact` | config、checkpoint、report、代码变更 |
| `decision-evidence` | 晋级、失败或停止的直接证据 |
| `note` | 必须由人理解、但无法图形化的简短说明 |

Agent 可以选择块的类型、数据来源、顺序和占用面积，但不能直接生成任意 HTML，也不能在没有证据来源时生成结果值。

## 5. 右侧下方：统一人机交互区

### 5.1 交互区的职责

右侧下方不是固定聊天框，也不是固定工具栏。它集中当前流程允许人执行的动作：

- 自然语言输入；
- 单选、多选和参数表单；
- 方法与算法选择；
- 调整搜索空间；
- 查看并覆盖 Agent 当前选择；
- 开始、暂停、停止、重试；
- 选择 baseline、candidate、seed 或 round；
- 选择数据处理方法；
- 请求补充图表或更换呈现方式；
- 导出图片、视频和报告；
- 打开原始 artifact 或代码。

普通流程默认由 Agent 自主推进。交互区提供的是持续可用的干预能力，不是每个节点都必须完成的审批表单。即使用户不做任何操作，流程也应在权限、资源和约束允许时继续执行。

### 5.2 上下文决定交互

交互区只显示当前节点可用的动作。

例如，在“选择算法”节点：

```text
当前采用：PPO（Agent 选择）
[改用 SAC] [改用 MADDPG] [查看候选比较]

训练预算  [100k steps]
并行环境  [8]
输入处理  [标准化 ▼]

自动推进：开启    [暂停] [修改后续计划]
```

在“评估结果”节点：

```text
[播放最佳 trial] [对比 baseline] [查看失败 seeds]
[扩大评估] [修改方法] [导出结果]
```

在异常节点：

```text
[跳转失败帧] [查看约束证据] [相同配置重试]
[返回方法选择] [打开原始日志]
```

### 5.3 对话与结构化操作共存

所有结构化动作都可以通过自然语言完成，但重要选择应同时提供明确控件。

例如用户可以输入“改用 SAC，观测做标准化，先跑 50k steps”，界面应把它解析成可见、可追溯的覆盖操作，并在最近的安全边界生效。普通、低风险且已授权的操作可以自主执行，但必须在流程、事件和产物中可见；只有高影响写操作、外部副作用或超出既有授权范围的操作需要等待确认。

## 6. 固定与自由的边界

产品采用“固定外壳 + 动态流程 + 受约束呈现”。

### 6.1 固定部分

- 左侧项目历史；
- 右侧上方流程与内容区；
- 右侧下方人机交互区；
- 项目、流程节点、事件、artifact 和结果的身份；
- 数据来源标记；
- 写操作的可见性、干预入口和审计；
- 失败、约束与权限边界。

### 6.2 Agent 可决定的部分

- 流程包含哪些节点；
- 哪些节点可以并行或循环；
- 当前节点最重要的信息；
- 使用回放、图表、分布、表格还是方法卡；
- 展示哪个指标、算法或处理方法；
- 哪些参数值得向人提供覆盖入口；
- 哪些详情默认折叠；
- 当前可用的下一步动作。

### 6.3 Agent 不可决定的部分

- 伪造状态或结果；
- 用文字覆盖原始实验结论；
- 隐藏失败约束；
- 静默执行高影响写操作；
- 绕过用户已经声明的冻结参数；
- 使用没有注册的数据源或任意脚本渲染 UI。

## 7. 最少必要信息机制

动态呈现不等于展示更多信息。每个流程节点采用三层信息密度。

### 7.1 第一层：当前必须知道

默认可见，只允许包含：

- 当前节点；
- 当前目标；
- 一个主要结果或问题；
- 最多三个关键证据；
- 当前可执行动作。

### 7.2 第二层：用于判断

用户展开后看到：

- 相关图表；
- 方法差异；
- 参数和搜索空间；
- seed/trial/round 对比；
- 约束详情。

### 7.3 第三层：用于追溯

进一步打开：

- 原始日志；
- JSON/YAML/CSV；
- checkpoint metadata；
- 代码变更；
- 命令与完整事件历史。

Agent 为呈现块声明 `priority` 与 `collapsed`，产品负责限制第一层的数量。

## 8. 方法选择示例

### 8.1 机器学习算法

项目当前已经注册 PPO、SAC、DDPG 和 MADDPG，也存在规则策略。Agent 可以根据动作空间、智能体数量、on/off-policy、训练预算和现有 baseline 选择适合的比较方式。

界面不固定显示所有算法细节。默认只呈现：

- 候选算法；
- 为什么进入候选；
- 与任务直接相关的一个优势和一个代价；
- 预计需要的训练预算；
- Agent 当前选择、备选方案和用户可干预项。

完整网络结构、buffer、optimizer 等信息按需展开。

### 8.2 数据或观测处理

Agent 可以为当前项目声明：

- 标准化或不处理；
- 帧堆叠；
- 通信延迟历史；
- 特征筛选；
- reward shaping；
- 数据过滤或异常值处理。

Agent 默认选择并执行处理方案；用户可以在运行前或运行中查看、覆盖或冻结这些选择。

每种选择必须关联：

- 输入来源；
- 输出去向；
- 会改变的实验配置；
- 冻结项；
- 如何验证效果。

### 8.3 呈现方式

同一“训练”节点可以根据方法变化：

- PPO：reward/loss/KL/entropy 与策略评估回放；
- SAC：actor/critic loss、Q 值和 replay buffer 相关指标；
- MADDPG：各 agent reward、联合 critic 和协作指标；
- 规则策略：参数搜索分布、轨迹、约束和 best config；
- 无训练 baseline：直接显示 replay 与评估指标。

因此呈现块由方法决定，而不是在产品代码中钉死一套训练 Dashboard。

## 9. 状态与数据模型

V2 区分四类状态。

### 9.1 项目状态

产品新增并持久化：

- `project_id`；
- 标题、创建和更新时间；
- 关联 artifact roots；
- 置顶、归档；
- 当前会话和用户输入历史。

这是会话管理需要的产品状态，不冒充实验结果。

### 9.2 流程声明

Agent 为项目生成可版本化的 `WorkflowSpec`：

```yaml
workflow_id: train_delay_policy_v1
execution_mode: autonomous
nodes:
  - id: define_task
    label: 定义任务
  - id: choose_method
    label: 选择算法与处理方法
    depends_on: [define_task]
    interventions: [override_method, override_processing, pause]
  - id: train
    label: 训练
    depends_on: [choose_method]
    interventions: [adjust_budget, pause, stop]
  - id: evaluate
    label: 评估与对比
    depends_on: [train]
```

WorkflowSpec 说明结构和可干预点，不把干预声明成必经审批。只有执行失败、用户主动暂停或缺少外部授权时，流程才停止自主推进。WorkflowSpec 不持续保存每个节点的 UI 进度。

### 9.3 项目事件

执行和人工操作写入追加式事件流：

```text
project.created
workflow.declared
node.entered
method.proposed
method.selected
command.started
artifact.produced
evaluation.completed
constraint.failed
human.overrode
human.paused
human.resumed
node.completed
```

流程位置由 WorkflowSpec 与事件流即时归约。这样既能支持自定义流程，也避免 Agent 同时维护多份进度状态。

### 9.4 实验事实

scenario、policy、experiment、suite 和 game 产物仍然是实验事实来源，包括：

- configs；
- manifests；
- replays；
- metrics；
- comparisons；
- checkpoints；
- reports；
- promotion 与 constraints。

## 10. 动态呈现协议

Agent 通过受限 `PresentationSpec` 选择当前页面内容。

示例：

```yaml
node_id: choose_method
execution_mode: autonomous
summary:
  title: 选择策略方法
  fact: 连续动作，3v3，多智能体对抗
  current_selection: ppo
blocks:
  - kind: method-choice
    source: registered_algorithms
    include: [ppo, sac, maddpg, rule_based]
    priority: 1
  - kind: comparison
    source: method_estimates
    fields: [sample_budget, coordination, stability]
    priority: 2
  - kind: artifact
    source: scenarios/vertical_wave_3v3_001/task_spec.yaml
    collapsed: true
interactions:
  - kind: override
    id: algorithm
  - kind: override
    id: observation_processing
  - kind: pause
    id: pause_after_current_run
```

关键限制：

- `kind` 必须来自注册块类型；
- `source` 必须可解析并在项目权限范围内；
- 结果值由 renderer 从 source 读取；
- Agent 只能提供方法理由或说明文字；
- 写操作必须在下方交互区可见并可追溯，只有高影响或超出授权范围的操作等待确认；
- 超过第一层数量限制的块自动折叠。

## 11. 新建项目体验

### 11.1 空白态

右侧上方只显示一个目标输入和少量可选入口：

- 从目标开始；
- 导入现有 game；
- 导入 suite run；
- 继续 experiment；
- 对比两个项目。

### 11.2 Agent 建议流程

用户提交目标后，Agent 返回：

- 一条精简流程；
- 当前采用的方法和第一个可干预位置；
- 当前已经识别的 artifact；
- 必要风险或冻结边界。

不展示“正在理解任务”“正在规划”等说明性步骤。

### 11.3 进入执行

用户提交目标后，流程默认直接进入执行；用户主动暂停或操作需要新增外部授权时除外：

- WorkflowSpec 被版本化；
- 事件流记录 Agent 选择和后续人工覆盖；
- 运行命令与 artifact 持续进入项目；
- 上方流程和呈现块根据事件与产物自动更新；
- 下方交互区切换为当前可用的干预动作。

## 12. 现有项目如何接入

### 12.1 50 场景 suite

导入一个 50 场景 suite run 时，系统创建或更新 50 个独立历史项目，并保留 suite 分组关系。每个项目只承载一个 scenario 的持续会话，例如：

```text
S47：读取场景 → baseline → candidate → 约束检查 → 差异分析
```

用户可以在左侧分别打开 S01、S02、S47 等项目，继续运行、干预或比较其中任意一个。打开 S47 时，Agent 在“差异分析”节点选择双回放、shape success 曲线和 constraint evidence；其他场景展示各自最相关的实验内容。

Suite 级聚合结果仍可作为分组总览、筛选和批量操作入口，但它不占用一个历史项目，也不替代 50 个单场景项目。

### 12.2 vertical_wave_3v3

流程可以呈现为交替最佳响应 round。进入某轮后，Agent 选择轨迹回放、双方 utility、target-side margin、trial 分布和 best-response gain。

### 12.3 PPO 实验

流程可以包含算法选择、观测处理、训练、评估。训练节点显示 PPO 相关曲线；评估节点切换为 replay、baseline/candidate 和 promotion evidence。

## 13. Human-in-the-loop

这里的 Human-in-the-loop 指“人始终有知情权和干预权”，不表示流程依赖人逐步审批。Agent 在已有权限和约束内自主运行；人可以观察、暂停、覆盖或改变后续，但不操作也不会阻止普通流程推进。

人必须能够知道：

- Agent 当前建议什么方法；
- Agent 为什么做出这项选择；
- 会修改哪些配置；
- 哪些参数保持冻结；
- 运行会消耗什么预算；
- 结果来自哪些 artifact；
- 下一步将发生什么。

常见可干预点：

- 覆盖 Agent 选择的算法或处理方法；
- 调整或冻结搜索空间和预算；
- 暂停当前运行并修改后续计划；
- 阻止可能改变实验结论的参数变更；
- 处理 constraint failure；
- 决定扩大评估、返回方法选择或停止项目；
- 导出、提交或发布结果。

干预在最近的安全边界生效，并写入事件流。只有三类情况需要流程停下：执行被错误或约束阻塞、用户主动暂停或设置显式复核点、下一步缺少必要的外部权限。干预权不是审批义务。

## 14. 技术架构调整

### 14.1 保留当前实验基础

继续复用：

- `RunRepository`；
- replay 和 visualization contracts；
- suite/game/experiment artifacts；
- 只读结果 API；
- 现有空间 renderer 或未来 Rerun 内核。

### 14.2 新增 Workbench 层

```text
Project Store
├── project metadata
├── conversation history
├── WorkflowSpec versions
├── append-only project events
├── PresentationSpec versions
└── artifact links

Execution Artifacts
├── game
├── scenarios
├── policies
├── experiments
└── suite_runs
```

Workbench 状态应存储在独立本地数据库或 `.autogame/` 目录并默认忽略提交。可分享的项目快照需要显式导出。

### 14.3 核心服务

- Project Service：创建、搜索、重命名、置顶和归档项目；
- Suite Importer：把 suite 中的每个 scenario 映射为独立项目，并维护可选分组；
- Workflow Reducer：从 WorkflowSpec 与事件流计算当前流程；
- Artifact Resolver：把呈现块的数据源解析到仓库产物；
- Presentation Renderer：渲染注册块并执行信息密度限制；
- Interaction Dispatcher：把用户选择转换为可检查的命令或配置变更；
- Evidence Index：建立 frame、event、metric、artifact 的关联；
- Viewer Kernel：负责空间、视频、图表和时间同步。

## 15. MVP 重新定义

### P0：项目会话骨架

- 新建项目；
- 左侧历史项目、搜索、重命名和归档；
- 导入现有 suite run 时生成逐场景历史项目，或导入一个 game；
- WorkflowSpec 与事件流；
- 默认自主执行，以及暂停、覆盖和恢复事件；
- 右侧流程位置；
- 下方统一对话与结构化交互区；
- 三种呈现块：`note`、`artifact`、`method-choice`。

### P1：实验内容闭环

- `spatial-replay`；
- `time-series`；
- `event-timeline`；
- `comparison`；
- `decision-evidence`；
- baseline/candidate 时间同步；
- S47 真实项目导入与运行。

### P2：方法自由度

- 读取算法 registry；
- 从 `get_config_schema()` 和 `search_space.yaml` 生成参数交互；
- PPO、SAC、DDPG、MADDPG 和规则策略的差异化呈现；
- 处理方法声明；
- WorkflowSpec 与 PresentationSpec 版本比较；
- 图片、视频和报告导出。

## 16. 验收场景

### 场景 A：新建 PPO 项目

1. 用户新建项目并输入目标；
2. Agent 声明任务特定流程；
3. Agent 选择 PPO 和观测处理方案并自主进入训练；
4. 上方显示当前选择、简短理由，以及 SAC 和规则策略两个合理备选；
5. 下方持续提供算法、处理方法、预算、暂停和停止入口；
6. 用户不操作时，训练与评估正常推进；
7. 用户改用 SAC 时，覆盖事件被记录并在安全边界生效；
8. 训练呈现随实际算法切换，评估节点显示 replay 与结果对比。

### 场景 B：导入 50 场景 suite

1. 用户导入现有 suite run；
2. 左侧生成或更新 50 个独立场景项目，并可折叠在同一 suite 分组下；
3. 用户打开 S47 项目，其流程由已有产物自动恢复；
4. 上方定位到 S47 的“差异分析”，只显示该场景的主要结论和 constraint failure；
5. 页面显示 S47 同步双回放与 shape success；
6. 下方提供查看证据、扩大评估、修改方法或停止该项目；
7. 用户可返回列表独立打开并继续其他 49 个项目。

### 场景 C：继续历史项目

1. 用户从左侧打开 3v3 项目；
2. 页面恢复当前流程、选中 round 和最近证据；
3. 不需要重新阅读完整聊天；
4. 下方只呈现当前相关的干预动作。

## 17. 验收原则

- 左侧历史项目能够恢复研究上下文，而不是只打开某个 artifact；
- 导入 50 场景 suite 后，左侧存在 50 个可独立继续的项目；
- 流程结构可以因项目而异；
- 在没有人工点击时，普通流程仍能自主完成；
- Agent 可以选择呈现块，但不能伪造数据；
- 第一层默认信息不超过一个结论、三个证据和当前动作；
- 选择算法后，训练呈现可以随算法改变；
- 产品不存在一套对所有实验钉死的 Dashboard；
- 项目流程状态可从 WorkflowSpec 和事件流重建；
- 人可以随时暂停、覆盖或改变后续，且这些干预能追溯到事件和配置变化；
- 正常流程不使用 `needs_input` 作为必经状态；
- 现有 replay、metrics、constraints 和 promotion 仍是实验事实来源。

## 18. 需要审核的产品决策

- [ ] 是否确认“项目会话”是产品最上层对象？
- [ ] 是否确认左侧固定为新建项目与历史项目列表？
- [ ] 是否确认右侧固定为“上方流程内容、下方人机交互”？
- [ ] 是否接受流程由 Agent 声明，而不是产品固定？
- [ ] 是否接受受限 PresentationSpec，让 Agent 选择呈现块和数据来源？
- [ ] 是否确认第一层信息密度限制：一个结论、最多三个证据？
- [ ] 是否接受新增项目事件流，用它推导流程位置？
- [ ] 是否确认普通流程默认自主推进，不依赖人的点击？
- [ ] 是否确认人始终拥有暂停、覆盖选择和修改后续计划的权利？
- [ ] 是否确认 Agent 的方法选择保持可见，但不设置必经审批？
- [ ] 是否确认导入 50 场景 suite 后生成 50 个历史项目，suite 仅作为分组？
- [ ] P0 是否应该包含真正的实验运行，还是先完成项目会话与导入？
- [ ] 项目历史默认存本机，是否符合首个版本定位？

## 19. 建议结论

建议采用以下产品基线：

1. 以“项目会话”取代“Suite 页面”作为产品入口；
2. 固定三段外壳，但允许流程和内容动态生成；
3. Agent 通过受限协议选择呈现，而不是维护一套固定 Dashboard；
4. 项目事件流连接对话、操作、artifact 和流程位置；
5. 实验事实与产品会话状态分层保存；
6. 流程默认自主推进，Human-in-the-loop 体现为持续知情、暂停和覆盖能力；
7. 导入 suite 时按 scenario 创建独立项目，suite 只承担分组与聚合；
8. 以“新建 PPO 项目”和“从 50 场景 suite 打开 S47 项目”作为首批验收场景。
