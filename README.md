# AutoGame 实验工作台

AutoGame 是一个面向博弈与多智能体实验的本地 Agent 工作台。用户给出目标，三个 Codex Agent 依次构造场景、选择方法、运行实验；工作台持续展示 Agent 行为、实验回放、指标和约束证据，并允许人随时干预。

它遵循两条产品原则：

- 自主运行是默认行为，人工操作不是流程必经审批。
- 人始终拥有知情权和干预权；界面展示真实事件与产物，不用固定百分比伪造进度，也不在 Agent 不可用时回退到 M1 固定规则。

## 能力概览

- 每个项目都是一条可恢复的 Codex thread，历史项目显示在左侧栏。
- 三阶段执行链：构造环境 → 选择方法 → 运行实验与评估。
- 50 个代表性场景作为 50 个独立历史项目浏览，而不是一个聚合任务。
- 统一呈现 2D/3D 回放、时间轴、指标曲线、Baseline/Candidate 对比和约束证据。
- 支持消息、修改方法、调整预算、暂停、恢复和停止。
- 执行完成、目标是否达成、是否晋级是三个独立状态。

## 环境要求

- Python 3.10 或更高版本。
- 可用的本地 Codex 登录环境。
- Git；使用 SSH 克隆时需先为 GitHub 配置 SSH key。

AutoGame 通过 Python Codex SDK 控制本地 Codex app-server。SDK 的安装方式、thread 生命周期和运行时要求见 [Codex SDK 官方文档](https://learn.chatgpt.com/docs/codex-sdk)。

## 安装

```bash
git clone git@github.com:OneFav/game-agent.git
cd game-agent
python -m venv .venv
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

`.[dev]` 会安装工作台、测试依赖和 `openai-codex`。只运行已有规则实验时无需创建 Codex thread；图形化工作台中的“新建项目”仍要求 Codex SDK 与三个 Agent 配置可用。

## 快速启动工作台

首次克隆后，先生成 50 场景套件的本地运行产物：

```bash
python -m game_agent validate-suite \
  --suite suites/max_space_50_v1/suite.yaml

python -m game_agent run-suite \
  --suite suites/max_space_50_v1/suite.yaml \
  --output suite_runs/max_space_50_v1
```

然后启动工作台：

```bash
python -m game_agent workbench \
  --run suite_runs/max_space_50_v1
```

浏览器打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。停止服务使用 `Ctrl+C`。

套件中断后可从已完成场景继续：

```bash
python -m game_agent run-suite \
  --suite suites/max_space_50_v1/suite.yaml \
  --output suite_runs/max_space_50_v1 \
  --resume
```

`suite_runs/` 是可复现的本地输出，默认不会提交到 Git。

## 图形化页面操作

### 1. 左侧：项目历史

- 点击“新建项目”创建一次新的 Agent 实验。
- 历史列表中的每一项都是独立项目；S01–S50 也分别作为独立历史项出现。
- 点击项目切换其流程状态、回放、指标、证据和操作记录。
- 项目状态来自真实运行事件，可显示运行中、已暂停、已停止、已完成或失败。

### 2. 上方：流程与 Agent 行为

主流程按“定义目标、构造环境、选择方法、运行实验、评估结果”组织。节点只在对应事件或必要产物存在时完成。

“Agent 动态”区域会记录 thread 启动或恢复、阶段进入、Agent 消息、命令执行、文件变化和失败信息。它用于回答“Agent 正在做什么、已经产出了什么”，而不是要求 Agent 额外维护一套展示状态。

### 3. 中部：实验内容与结果

- 回放：切换 Baseline / Candidate、seed、2D / 3D 视角和图层；播放、暂停或拖动时间轴查看任意帧。
- 指标：查看主指标曲线、Baseline、Candidate 和差值。
- 约束：查看碰撞、越界、动作合法性等证据，并可跳转到相关回放时刻。
- 结论：单独显示目标结果和晋级结果。工作流执行完成不等于实验目标达成。
- 如果某类实验没有可回放数据，页面显示 Agent 的文字结果和现有产物，不生成虚假动画或指标。

页面展示哪些图、指标和证据由场景的 visualization contract 与实验产物决定，因此可以适配不同算法和任务，不需要把内容固定成一种无人机模板。

### 4. 下方：Human in the loop

流程默认自主推进，但以下控制始终可用：

- “发送消息”：向当前 Codex turn 追加目标、约束或解释请求。
- “修改方法”：要求 Agent 改变算法、基线或处理路径。
- “调整预算”：改变训练轮数、seed、时间或计算预算。
- “暂停”：中断当前 turn 并保留项目和 thread。
- “恢复”：在同一项目上继续未完成阶段。
- “停止”：终止当前执行；已有真实产物仍然保留。

干预会作为项目事件保存在本机，不会改写已经发生的实验事实。

## 新建真实 Agent 项目

1. 打开工作台，点击左侧“新建项目”。
2. 填写简短标题和“目标描述”。
3. 提交后，工作台启动持久 Codex thread，并依次调用：
   - `.codex/agents/scenario_compiler.toml`
   - `.codex/agents/policy_designer.toml`
   - `.codex/agents/experiment_autoresearch.toml`
4. 在页面中观察行为、回放和证据；需要时从底部干预。

推荐目标描述至少包含：任务与参与方、优化目标、硬约束、可用预算或 seeds、希望看到的结果形式。例如：

> 在二维双机穿环场景中，提高红方穿环成功率；碰撞率和越界率必须为 0。使用 3 个评估 seed，在小预算内比较 Baseline 与 Candidate，并输出轨迹回放、成功率曲线和失败证据。

启动服务后可检查 Agent 配置状态：

```bash
curl http://127.0.0.1:8765/health
```

`agent.ready` 应为 `true`。如果页面提示 Agent 无法启动，依次检查 Python 环境中是否安装 `openai-codex`、上述三个 TOML 是否存在，以及本地 Codex 登录/运行时是否可用。AutoGame 不提供固定规则回退。

## 状态语义

| 状态 | 回答的问题 |
|---|---|
| 流程状态 | Agent 是否仍在执行，执行到哪个阶段 |
| 目标结果 | 实验目标是 `met`、`not_met`、`inconclusive` 还是 `blocked` |
| 晋级结果 | Candidate 是否在相同条件下优于 Baseline 且通过硬约束 |

因此“运行已完成”只表示流程结束，不代表指标是 100%，也不代表 Candidate 自动晋级。

## CLI

| 命令 | 用途 |
|---|---|
| `validate-suite` | 校验冻结场景套件 |
| `run-suite` | 独立、可恢复地运行场景套件 |
| `render-suite` | 重新生成现有套件的汇总图 |
| `workbench` | 启动实验工作台 |
| `view-suite` | `workbench` 的兼容别名 |
| `compile-scenario` | 从任务描述生成场景包 |
| `build-policy` | 为场景生成策略包 |
| `run-experiment` | 运行单个实验包 |
| `run` | 依次执行旧版单项目 CLI 流水线 |

使用 `python -m game_agent --help` 或在子命令后加 `--help` 查看完整参数。

## 目录结构

```text
game-agent/
├── .codex/agents/          # 三个工作台 Agent 配置
├── src/
│   ├── contracts/          # 场景、策略、运行时与可视化契约
│   ├── game_agent/
│   │   ├── scenarios/      # 50 场景目录与运行时
│   │   ├── visualization/  # 工作台服务、状态映射和前端
│   │   ├── autoresearch/   # 实验、套件和结果生成
│   │   ├── policy_designer/
│   │   └── rl/
│   └── hooks/              # 阶段产物验证
├── suites/                 # 可复现套件定义
├── scenarios/              # 有界场景产物
├── policies/               # 有界策略产物
├── experiments/            # 有界实验产物
├── game/                   # 项目计划与研究记录
├── docs/product-design/    # 产品方案、竞品调研和平面设计
└── tests/                  # pytest 回归测试
```

工作台项目索引与干预事件保存在 `.autogame/`；本地新项目以 `local-*` 产物目录保存。这些路径和 `suite_runs/`、`output/`、`ppt/` 都默认忽略，避免上传个人路径、运行日志和大体积临时文件。

## 测试

```bash
python -m pytest -q
```

也可以只运行工作台相关测试：

```bash
python -m pytest \
  tests/test_visualization_repository.py \
  tests/test_visualization_service.py \
  tests/test_workbench_executor.py -q
```

## 隐私与发布

- 不要在目标描述、Agent 消息、配置或实验产物中写入密钥、token 和个人数据。
- 不要提交 `.autogame/`、`local-*`、`suite_runs/`、虚拟环境或缓存。
- 公开参考产物必须使用仓库相对路径，不记录本机用户目录。
- 提交前建议运行：`git status --short` 和仓库级敏感信息扫描。

## 当前边界

- 环境主要用于可验证研究流程，不等同于高保真飞行仿真器。
- 不同任务提供的图表和回放能力取决于各自的可视化契约与真实产物。
- Codex thread 依赖本地 SDK、登录状态和运行时；缺少配置时工作台会明确失败。
- 大规模训练仍需外部算力、队列和制品存储集成。
