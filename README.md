# Game Agent

三 Agent 架构的 M1 垂直切片——将半自由自然语言无人机博弈任务转化为可验证的场景包、策略包和 AutoResearch 实验包。


---

## 安装

```bash
git clone <this-repo> && cd game-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Python ≥ 3.10，依赖 `numpy`、`PyYAML`；可视化可选 `matplotlib`、`gymnasium`。

---

## 使用方式

登入 Codex 后，通过以下 Skill 完成从初始化到全流程自动科研：

### 初始化项目

```
$game-init "<场景描述>"
```

读取现有代码规范与模板，生成 `game/<game-id>/plan.md` 初步实施计划。

### 全流程开发

```
$game-main <game-id> [--max-hours X]
```

按照 `plan.md` 依次调用三 Codex subagent（scenario_compiler → policy_designer → experiment_autoresearch），完成场景编译、策略生成和确定性 sweep 实验。`--max-hours` 为可选的时间上限。

### 迭代优化至可视化

```
/goal 根据 plan.md 迭代优化策略配置，直到满足指标要求并输出 2D/3D 可视化结果
```

在已有实验基础上继续调优，直至产出满足 plan.md 中预期指标的可视化报告。

---

## 示例场景（提示词）

将以下描述粘贴到 `$game-init` 命令中即可启动对应项目。

### 示例 1：基础双人穿环

> 红方无人机穿过两个圆环，蓝方追击拦截，完美通信，超时 60 步。

*drone_ring_game · success_rate ≥ 0.7*

### 示例 2：通信延迟穿环

> 红方无人机穿过两个圆环，蓝方追击拦截，通信延迟 2 步，超时 100 步。

*drone_ring_game · success_rate ≥ 0.55*

### 示例 3：丢包通信多环

> 红方无人机穿过三个圆环，蓝方追击拦截，丢包 10%，超时 200 步。

*drone_ring_game · success_rate ≥ 0.4*

### 示例 4：3D 回转门双人对抗

> 红蓝双方各 1 架赛车机在 slalom 布局下 3D 对抗，完美通信，DoubleIntegrator3D 动力学，超时 400 步。

*swarm_combat · team_score ≥ 1.0*

### 示例 5：编队护航 2v2

> 红方 2 机（1 赛车机+1 防守机护航）对阵蓝方 2 机（1 赛车机+1 防守机拦截），wide_slalom 布局，超时 600 步。防守机护航己方赛车机，拦截对方赛车机。

*swarm_combat · team_score ≥ 2.0*

### 示例 6：大规模编队 3v3

> 红方 3 机（2 赛车机+1 防守机）对阵蓝方 3 机（2 赛车机+1 防守机），vertical_wave 布局，随机出生，超时 800 步。需要多车道分配和前视碰撞检测。

*swarm_combat · team_score ≥ 3.0*

### 示例 7：8 字形全编队 4v4

> 红方 4 机（2 赛车机+2 防守机）对阵蓝方 4 机（2 赛车机+2 防守机），figure_eight 布局，双向穿门，DampedDoubleIntegrator3D 动力学，超时 1200 步。全参数空间 sweep，需要输出 3D 可视化。

*swarm_combat · team_score ≥ 4.0*

---

## CLI 子命令

| 命令 | 功能 | 输出 |
|------|------|------|
| `run` | 完整 M1 链路 | scenarios/ + policies/ + experiments/ + report.md + task.md |
| `compile-scenario` | 仅编译场景包 | `scenarios/<task_id>/` |
| `build-policy` | 仅生成策略包 | `policies/<policy_id>/` |
| `run-experiment` | 仅运行实验 | `experiments/<exp_id>/` |

## 项目结构

```text
game-agent/
├── src/
│   ├── game_agent/                   # 核心包（cli + 三 Agent + 环境 + 工具）
│   │   ├── scenario_compiler/        # Agent 1：场景编译器
│   │   ├── policy_designer/          # Agent 2：策略设计器 + reference_policies/
│   │   ├── autoresearch/             # Agent 3：确定性 sweep 实验
│   │   ├── envs/
│   │   │   ├── drone_ring_game/      # 轻量 2D 基线
│   │   │   └── swarm_combat/         # 模块化 3D 多无人机对抗（12 模块）
│   │   └── utils/                    # fs / manifest / errors
│   ├── contracts/                    # Policy ABC + Scenario Schema
│   └── hooks/                        # 三阶段硬验证脚本
├── tests/                            # 54 个测试
├── .codex/agents/                    # 三 Codex subagent TOML
├── .agents/skills/                   # 五 Skill 定义
├── docs/                             # 设计文档 + 模板说明
├── game/                             # Game-init 产出（plan.md + log.md + summary.md）
├── scenarios/  policies/  experiments/  # 参考产物
└── pyproject.toml
```

## 支持的任务族

| 族 | 环境 | 策略 | 场景数 |
|----|------|------|--------|
| **drone_ring_game** | 2D 点质量，2 agent | RuleRingNavigationPolicy | perfect / delayed / lossy |
| **swarm_combat** | 3D 双积分器，N vs N | SafeRulePolicy | 5 种门布局 × 多角色 × 随机出生 |

## 三 Agent 流水线

```
自然语言任务
  → [Agent 1: Scenario Compiler]  → scenarios/<task_id>/
  → [Hook: post_scenario_compile]
  → [Agent 2: Policy Designer]    → policies/<policy_id>/
  → [Hook: post_policy_submit]
  → [Agent 3: AutoResearch]       → experiments/<exp_id>/
  → [Hook: post_experiment_run]
```

每个 Agent 仅允许写入自己的产物目录，禁止修改 contracts/、hooks/、src/ 下的共享代码。

## 测试

```bash
python -m pytest -v                  # 全量（54 passed）
python -m pytest tests/test_scenario_compiler.py -v
python -m pytest tests/test_policy_designer.py -v
python -m pytest tests/test_autoresearch.py -v
```

## 已知限制

- 自然语言解析为规则匹配，不是通用 NLP
- 环境动力学为点质量 + 双积分器，不是高保真无人机仿真
- 策略主链路为规则策略，训练入口为轻量骨架
- AutoResearch 为单进程确定性 sweep，不覆盖大规模分布式实验
