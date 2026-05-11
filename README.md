# Game Agent

Game Agent 是一个三 Agent 架构的 M1 垂直切片项目，用于把半自由自然语言无人机博弈任务转化为可验证的场景包、规则策略包和确定性 AutoResearch 实验结果。

当前版本聚焦简化的 `drone_ring_game` 任务族：红方无人机穿过圆环，蓝方无人机追击并尝试拦截；场景可表达通信延迟、丢包、超时步数、硬约束和评估指标。

> 边界说明：本项目当前不是通用无人机仿真平台，也不是完整 RL 框架；它实现的是可运行、可验证、可扩展的 M1 端到端闭环。

## 核心能力

- **Scenario Compiler**：从半自由自然语言任务生成 `scenarios/<task_id>/`。
- **Policy Designer**：从已验证场景生成 `policies/<policy_id>/` 规则策略包。
- **Experiment AutoResearch**：对冻结的场景和策略执行确定性小规模 sweep，生成 `experiments/<exp_id>/`。
- **Validation Hooks**：在每个阶段检查接口契约、必需文件、指标结构和生成包可用性。
- **CLI Orchestration**：通过一个命令串联完整 M1 流程。
- **Agent Project Content**：包含三 Agent 的工作边界、提示词、薄封装 orchestrator 和本地 skill 描述。

## 项目结构

```text
.
├── agents/                         # 三个项目 Agent 的职责、提示词和薄封装 orchestrator
│   ├── scenario_compiler/
│   ├── policy_designer/
│   └── experiment_autoresearch/
├── .agents/skills/                 # 项目本体使用的本地 skill
│   ├── scenario-spec-compiler/
│   ├── policy-interface-builder/
│   └── autoresearch-loop/
├── contracts/                      # 场景 schema 与策略协议
├── game_agent/                     # Python 包主体
│   ├── autoresearch/               # 确定性 sweep 与指标排名
│   ├── envs/drone_ring_game/       # 轻量无人机圆环博弈环境
│   ├── policy_designer/            # 策略包生成器
│   ├── scenario_compiler/          # 场景包生成器
│   ├── utils/                      # YAML/JSON/manifest/文件系统工具
│   └── cli.py                      # CLI 入口
├── hooks/                          # 阶段后验证脚本
├── tests/                          # 单元测试、契约测试和 smoke 测试
├── report.md                       # 当前可解决任务族说明
├── task.md                         # 后续剩余任务
└── pyproject.toml
```

## 环境要求

- Python `>=3.10`
- 运行依赖：
  - `numpy>=1.24`
  - `PyYAML>=6.0`
- 开发/测试依赖：
  - `pytest>=7.4`

## 安装

建议在虚拟环境中安装：

```bash
python -m venv .venv
# Windows PowerShell
. .venv/Scripts/Activate.ps1

python -m pip install -e ".[dev]"
```

如果不使用 editable install，也可以在仓库根目录直接运行测试和 CLI，因为 `pyproject.toml` 已为 pytest 配置 `pythonpath = ["."]`。

## 快速开始

运行完整 M1 链路：

```bash
python -m game_agent run \
  --project-root .tmp-m1-demo \
  --task "红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 60 步" \
  --task-id drone_ring_001 \
  --policy-id rule_ring_nav_v1 \
  --exp-id exp_drone_ring_001
```

成功后会生成：

```text
.tmp-m1-demo/
├── scenarios/drone_ring_001/
├── policies/rule_ring_nav_v1/
├── experiments/exp_drone_ring_001/
├── report.md
└── task.md
```

## CLI 用法

查看命令：

```bash
python -m game_agent --help
```

### 1. 端到端运行

```bash
python -m game_agent run \
  --project-root <output-root> \
  --task "<自然语言任务>" \
  --task-id <task_id> \
  --policy-id <policy_id> \
  --exp-id <exp_id>
```

该命令依次执行：

1. `ScenarioCompiler.compile(...)`
2. `hooks/post_scenario_compile.py`
3. `PolicyDesigner.build(...)`
4. `hooks/post_policy_submit.py`
5. `AutoResearchRunner.run(...)`
6. `hooks/post_experiment_run.py`
7. 写入根级 `report.md` 与 `task.md`

### 2. 只生成场景包

```bash
python -m game_agent compile-scenario \
  --project-root <output-root> \
  --task "<自然语言任务>" \
  --task-id <task_id>
```

输出：`<output-root>/scenarios/<task_id>/`

### 3. 只生成策略包

```bash
python -m game_agent build-policy \
  --project-root <output-root> \
  --scenario <task_id 或 scenarios/<task_id>> \
  --policy-id <policy_id>
```

输出：`<output-root>/policies/<policy_id>/`

### 4. 只运行 AutoResearch

```bash
python -m game_agent run-experiment \
  --project-root <output-root> \
  --scenario <task_id 或 scenarios/<task_id>> \
  --policy <policy_id 或 policies/<policy_id>> \
  --exp-id <exp_id>
```

输出：`<output-root>/experiments/<exp_id>/`

## 三 Agent 架构

### Agent 1：Scenario Compiler

- 输入：半自由自然语言无人机任务。
- 输出：`scenarios/<task_id>/`。
- 责任：抽取任务族、角色、圆环数量、通信约束、超时、formalism、动作空间、观测空间、终止条件和评估指标。
- 验证：

```bash
python hooks/post_scenario_compile.py --scenario scenarios/<task_id>
```

### Agent 2：Policy Designer

- 输入：已验证的场景包。
- 输出：`policies/<policy_id>/`。
- 责任：生成规则策略、训练入口、推理入口、默认配置、搜索空间、算法卡和策略包测试。
- 关键约束：动作必须符合场景 action bounds，并在返回环境前 clip。
- 验证：

```bash
python hooks/post_policy_submit.py --policy policies/<policy_id>
```

### Agent 3：Experiment AutoResearch

- 输入：冻结的场景包与策略包。
- 输出：`experiments/<exp_id>/`。
- 责任：按搜索空间执行确定性 sweep、多 seed 评估、leaderboard 排序、best config 选择和报告生成。
- 关键约束：晋升和排名使用 `evaluation_metrics`，不使用 reward components 作为真值来源。
- 验证：

```bash
python hooks/post_experiment_run.py --exp experiments/<exp_id>
```

## 生成物说明

### ScenarioPackage

典型文件：

```text
scenarios/<task_id>/
├── task_spec.yaml
├── env_config.yaml
├── env.py
├── model.md
├── assumptions.md
├── tests/
└── manifest.json
```

### PolicyPackage

典型文件：

```text
policies/<policy_id>/
├── policy.py
├── train.py
├── infer.py
├── default_config.yaml
├── search_space.yaml
├── algorithm_card.md
├── requirements.txt
├── tests/
├── metadata.json
└── manifest.json
```

### ExperimentPackage

典型文件：

```text
experiments/<exp_id>/
├── trials/
│   └── trial_0001/
│       ├── config.yaml
│       ├── metrics.json
│       └── log.json
├── leaderboard.csv
├── best_config.yaml
├── report.md
└── manifest.json
```

## 验证与测试

运行全量测试：

```bash
python -m pytest -v
```

当前验证基线：

```text
52 passed
```

也可以分阶段运行：

```bash
python -m pytest tests/test_scenario_compiler.py -v
python -m pytest tests/test_policy_designer.py -v
python -m pytest tests/test_autoresearch.py -v
python -m pytest tests/test_hooks.py -v
python -m pytest tests/test_cli_smoke.py -v
python -m pytest tests/test_agent_project_content.py -v
```

## 当前支持的任务族

当前 M1 支持 `drone_ring_game`：

- 红方无人机需要穿过一个或多个圆环。
- 蓝方无人机追击并尝试拦截。
- 可配置通信延迟、丢包概率和超时步数。
- 主要评估指标为成功率。
- 硬约束包括碰撞率、出界率和动作违规率。

更多边界说明见 [report.md](report.md)，剩余任务见 [task.md](task.md)。

## 设计原则

- **KISS**：M1 只保留可运行闭环所需的最小实现。
- **YAGNI**：不预置未使用的大型 RL 训练框架或复杂仿真依赖。
- **DRY**：共享文件系统、manifest、指标和 hook 验证逻辑。
- **SOLID**：场景编译、策略生成、实验评估和验证职责分离。

## 已知限制

- 自然语言解析是面向 M1 的轻量规则解析，不是通用 NLP 系统。
- 环境动力学是轻量几何模型，不是高保真无人机仿真。
- 策略主链路是规则策略，训练入口是轻量骨架。
- AutoResearch 只执行确定性小规模 sweep，不覆盖大规模分布式实验。
- 当前任务族聚焦 `drone_ring_game`，新任务族需要扩展 schema、环境、策略模板和指标。

## License

当前仓库尚未声明 License。发布或对外共享前请补充明确的授权条款。
