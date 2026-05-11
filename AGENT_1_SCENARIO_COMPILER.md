# Scenario Compiler Agent — 仓库架构与功能

> **角色定位**: 自然语言任务 → 形式化场景规格的**编译器**
> **负责人**: 朋友
> **核心红线**: 定义问题,不解决问题。不能改算法,不能改评价指标。

---

## 0. 一句话职责

把一段无人机对抗任务的**自然语言描述**,编译成一个**冻结的、可被下游消费的场景包** (`scenarios/<task_id>/`),输出物的 schema 严格遵守 `contracts/scenario_schema.yaml`。

---

## 1. 在仓库中的位置

```
auto_drone_research/
├── agents/
│   └── scenario_compiler/
│       ├── AGENTS.md              ← 本 agent 的运行规则
│       ├── prompt.md              ← 系统提示词模板
│       └── orchestrator.py        ← 编排逻辑(可选)
│
├── .agents/skills/                ← 共享技能,本 agent 主要使用前 5 个
│   ├── scenario-spec-compiler/
│   ├── posg-modeling/
│   ├── communication-modeling/
│   ├── env-contract-testing/
│   └── reward-eval-separation/
│
├── hooks/                         ← 硬验证脚本
│   ├── pre_scenario_compile.py
│   └── post_scenario_compile.py
│
├── scenarios/                     ← 本 agent 唯一的写权限目录
│   └── <task_id>/
│
├── envs/                          ← 环境基座,本 agent 可写但需谨慎
│   └── drone_ring_game/
│
├── contracts/                     ← 只读,所有 agent 共享
│   └── scenario_schema.yaml
│
└── mcp/                           ← 可选 MCP 服务
    ├── scenario_db_server.py
    └── simulator_metadata_server.py
```

---

## 2. AGENTS.md 思路

`agents/scenario_compiler/AGENTS.md` 是本 agent 的**长期约束**,LLM 每次启动都会读取。它不是教程,是**法律文件**:写得越短越好,但每条必须可执行、可验证。

### 2.1 必须包含的章节

```markdown
# Scenario Compiler Agent

## Mission
Convert a natural-language drone game task into a formal, validated scenario package.
The output must be precise enough for policy and experiment agents to consume 
without reinterpretation.

## Inputs
- Natural language task description.
- Base environment family (e.g., drone_ring_game).
- Existing scenario templates in scenarios/.
- User-provided constraints.

## Outputs
A scenario directory `scenarios/<task_id>/` containing:
- task_spec.yaml
- model.md
- env_config.yaml
- env.py
- assumptions.md
- tests/
- manifest.json

## Allowed Edits
- scenarios/<task_id>/         (write)
- envs/<family>/configs/       (write, non-invasive)
- scenario-specific tests       (write)

## FORBIDDEN Edits
- algorithms/                   (NEVER)
- policies/                     (NEVER)
- experiments/                  (NEVER)
- evaluator/                    (NEVER)
- contracts/                    (NEVER)
- hooks/                        (NEVER)

## Hard Constraints
1. All numerical defaults must be recorded in assumptions.md.
2. reward_structure and evaluation_metrics MUST be separate in task_spec.yaml.
3. All scenarios must support deterministic reset given a seed.
4. Communication mode must be one of the 5 enum values, not silently assumed.
5. Every scenario must produce passing contract tests before freeze.

## Required Validation Commands
Before considering work complete, the agent MUST run:
\```bash
python hooks/post_scenario_compile.py --scenario scenarios/<task_id>
python -m pytest scenarios/<task_id>/tests
\```

## Done Definition
A scenario is done only when:
- Schema validation passes
- All contract tests pass  
- assumptions.md is non-empty
- manifest.json contains freeze_hash
- No file outside scenarios/<task_id>/ has been modified
```

### 2.2 写 AGENTS.md 的三条原则

1. **强动词**: "MUST", "NEVER", "FORBIDDEN" 比 "should" 更有约束力
2. **可执行的 Done 定义**: "通过测试" > "代码看起来对"
3. **明确禁止区**: 列出"不能写的目录"比列出"能写的目录"更重要(LLM 容易越界)

---

## 3. skills/ 思路

skills 是**可复用的能力包**,每个 skill 是一个目录,核心文件是 `SKILL.md`。本 agent 重点使用以下 5 个 skill。

### 3.1 `scenario-spec-compiler` (核心 skill)

```
.agents/skills/scenario-spec-compiler/
├── SKILL.md                  ← 描述何时触发、做什么、产出什么
├── scripts/
│   ├── extract_parameters.py ← 从自然语言抽取数值参数
│   ├── instantiate_template.py ← 把参数填入任务族模板
│   └── validate_spec.py
├── references/
│   ├── task_family_examples/ ← 已有任务的 task_spec.yaml 样本
│   └── parameter_glossary.md ← 自然语言术语 ↔ 形式化字段 对照表
└── templates/
    ├── drone_ring_game.yaml.tmpl
    └── pursuit_evasion.yaml.tmpl
```

**SKILL.md 要点**:
```markdown
# scenario-spec-compiler

## When to use
Triggered when: 用户输入"设计一个任务"、"构建场景"、"把自然语言变成环境配置"。

## What it does
自然语言 → 任务族识别 → 参数抽取 → 模板实例化 → task_spec.yaml + assumptions.md

## Inputs
- raw natural language task
- allowed_task_family list

## Outputs
- scenarios/<task_id>/task_spec.yaml (符合 scenario_schema.yaml)
- scenarios/<task_id>/assumptions.md (列出所有默认值)

## Critical rule
任何在自然语言中**未明确指定**的数值或选择,必须:
1. 选择保守默认值
2. 在 assumptions.md 中显式列出
绝不允许"沉默地"补全字段。
```

### 3.2 `posg-modeling`

```
.agents/skills/posg-modeling/
├── SKILL.md
├── references/
│   ├── mdp_vs_posg_decision_tree.md  ← 何时该用哪个 formalism
│   └── pettingzoo_parallel_api.md
└── templates/
    └── model_md.tmpl  ← model.md 的标准模板
```

**职责**:判断任务应该建模为 MDP / Markov Game / POSG / Dec-POMDP,生成 `model.md`。

**触发条件**: 出现以下任一关键词 → 必须输出 POSG 或 Dec-POMDP:
- "对抗"、"博弈"、"红蓝双方"
- "通信受限"、"丢包"、"延迟"
- "局部观测"、"看不到"

### 3.3 `communication-modeling`

把"完美通信 / 有限通信 / 延迟 / 丢包 / 无通信"五种模式转成 task_spec 中的 `communication` 字段。

**关键约束**: 通信模式必须是 5 个枚举值之一,**禁止隐式假设**。如果自然语言没有提到通信,必须主动询问或在 `assumptions.md` 中显式标注 "默认完美通信"。

### 3.4 `env-contract-testing`

自动生成场景级 contract tests。基于 task_spec 中的字段,生成对应的 pytest 文件。

**生成模板**:
- `test_reset_deterministic.py`: 验证 `reset(seed=0)` 两次结果一致
- `test_obs_action_shape.py`: 验证 obs/action shape 与 spec 一致
- `test_termination.py`: 每种 termination 条件至少有一个触发用例
- `test_collision_detection.py`: 在已知碰撞配置下必须检测到
- `test_communication.py`: 仅当 communication.mode != "perfect" 时生成

### 3.5 `reward-eval-separation`

**唯一职责**: 检查 `task_spec.yaml` 中 `reward_structure` 和 `evaluation_metrics` 是否独立。

**检查规则**:
- `evaluation_metrics.primary` 不能是 `reward_structure.components` 中任一项的简单线性组合
- `evaluation_metrics.hard_constraints` 不能在 `reward_structure` 中作为可优化目标出现
- 如果检测到混淆 → 输出 `WARNING: potential reward hacking risk`

---

## 4. hooks 思路

hooks 是**不可绕过的硬验证**,由 orchestrator 或 CI 在 agent 工作前后自动运行。

### 4.1 `pre_scenario_compile.py`

**运行时机**: agent 开始工作之前
**职责**: 检查输入是否完整

```python
# 伪代码
def main(natural_language_task, base_environment):
    required_fields = check_natural_language(natural_language_task, [
        "agent_count",
        "task_objective",
        "action_type",
        "observation_mode",
        "communication_mode",
        "termination_condition",
        "safety_constraint",
    ])
    
    missing = [f for f in required_fields if not f.found]
    
    if missing:
        # 不阻断,但要求 agent 在 assumptions.md 中显式标注
        return {
            "status": "warn",
            "missing_fields": missing,
            "instruction": "Fill defaults and document in assumptions.md"
        }
    return {"status": "ok"}
```

### 4.2 `post_scenario_compile.py`

**运行时机**: agent 声称完成之后
**职责**: 全面 schema + 测试 + 哈希校验

```python
def main(scenario_path):
    checks = [
        check_schema(f"{scenario_path}/task_spec.yaml"),
        check_model_md_sections(f"{scenario_path}/model.md"),
        check_env_loadable(f"{scenario_path}/env.py"),
        check_reset_deterministic(scenario_path, seed=0),
        check_obs_action_shape(scenario_path),
        run_pytest(f"{scenario_path}/tests"),
        check_no_forbidden_edits(),  # 检查 agent 没有改 algorithms/ 等
        check_assumptions_non_empty(f"{scenario_path}/assumptions.md"),
    ]
    
    if all(c.passed for c in checks):
        # 计算 freeze_hash 并写入 manifest.json
        write_manifest(scenario_path, frozen=True)
        return "frozen"
    else:
        return "rejected", [c for c in checks if not c.passed]
```

---

## 5. MCP 服务思路 (可选)

MCP 是**外部工具入口**,本 agent 第一版不强制使用。

### 5.1 `scenario_db_server.py`

提供已有任务模板查询:
- `list_templates()` → `["drone_ring_game_v0", "pursuit_evasion_v0", ...]`
- `get_template(name)` → 返回 task_spec 模板
- `find_similar_scenarios(natural_language)` → 检索语义相似的历史场景

**价值**: 防止 agent 每次都从零生成,鼓励复用稳定模板。

### 5.2 `simulator_metadata_server.py`

提供环境基座能力说明:
- `get_supported_dynamics()` → `["point_mass_3d", "quadrotor_6dof"]`
- `get_supported_observations()` → `["full_state", "partial_state", "limited_comm"]`
- `validate_config(env_config)` → 检查配置是否被基座支持

**价值**: agent 在生成 `env_config.yaml` 时不会产出"基座不支持的字段"。

---

## 6. 内部工作流程

```
[输入] 自然语言任务
    ↓
[hook] pre_scenario_compile.py 检查关键字段
    ↓
[skill] scenario-spec-compiler: 抽取参数 + 任务族识别
    ↓
[skill] posg-modeling: 判断 formalism + 生成 model.md
    ↓
[skill] communication-modeling: 处理通信子模型
    ↓
[skill] scenario-spec-compiler: 生成 task_spec.yaml
    ↓
[skill] env-contract-testing: 生成 tests/
    ↓
[skill] reward-eval-separation: 检查 reward / metric 独立性
    ↓
[内部] 生成 env.py (基于环境基座 + env_config.yaml)
    ↓
[hook] post_scenario_compile.py 全面校验
    ↓
[冻结] 写入 manifest.json + freeze_hash
    ↓
[输出] scenarios/<task_id>/ 准备好被下游消费
```

---

## 7. 失败模式与对策

| 失败模式 | 对策 |
|---|---|
| 自然语言模糊导致默认值过多 | `assumptions.md` 强制要求列出每个默认值的来源,超过 N 项触发 `clarification_request.md` 回退到用户 |
| 生成的 env.py 不可加载 | `post_scenario_compile.py` 强制 `import + reset` smoke test,失败直接 reject |
| reward 和 evaluation 混淆 | `reward-eval-separation` skill 自动扫描 |
| 测试覆盖不足 | `env-contract-testing` 强制生成最小测试集,缺一个就 fail |
| 越权修改 algorithms/ | `post_scenario_compile.py` 调用 `git diff` 检查改动范围 |

---

## 8. 与其他 agent 的边界

| 场景 | 本 agent | 策略 agent | 实验 agent |
|---|:---:|:---:|:---:|
| 写 `task_spec.yaml` | ✓ | ✗ | ✗ |
| 改 `reward_structure` | ✓ | ✗ | ✗ |
| 写 `policy.py` | ✗ | ✓ | ✗ |
| 改 `evaluation_metrics` | ✗ | ✗ | ✗ |
| 决定 `splits.hidden_test` 内容 | ✓(只规定路径) | ✗ | ✗ |

**最重要的边界**: 本 agent **是评价指标的最终定义者**。一旦冻结,所有下游 agent 都按这个指标衡量成败,不能反向修改。
