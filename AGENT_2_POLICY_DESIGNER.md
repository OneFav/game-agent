# Policy Designer Agent — 仓库架构与功能

> **角色定位**: 形式化场景规格 → 可运行 policy package 的**设计器**
> **负责人**: 朋友
> **核心红线**: 解决问题,不修改问题。不能改环境,不能改评价指标,不能偷看 hidden tests。

---

## 0. 一句话职责

读取一个**冻结的场景包** (`scenarios/<task_id>/`),设计并实现一个满足 `contracts/policy_protocol.py` 协议的**策略包** (`policies/<policy_id>/`),包括代码、训练入口、推理入口、算法卡片。

**输出物会被实验 agent 视为黑盒。** 策略 agent 必须把所有需要的信息显式写入策略包,不能依赖任何隐含约定。

---

## 1. 在仓库中的位置

```
auto_drone_research/
├── agents/
│   └── policy_designer/
│       ├── AGENTS.md              ← 本 agent 的运行规则
│       ├── prompt.md              ← 系统提示词
│       └── orchestrator.py
│
├── .agents/skills/                ← 共享技能,本 agent 主要使用 6 个
│   ├── policy-interface-builder/
│   ├── algorithm-selector/
│   ├── mpc-policy-template/
│   ├── mappo-policy-template/
│   ├── safety-shield-builder/
│   └── algorithm-card-writer/
│
├── hooks/
│   ├── pre_policy_submit.py
│   ├── post_policy_submit.py
│   └── safety_gate.py
│
├── algorithms/                    ← 算法库,本 agent 可写
│   ├── baselines/
│   │   └── rule_based_ring_nav/
│   ├── mpc/
│   │   └── mpc_interceptor/
│   ├── mappo/
│   │   └── mappo_velocity/
│   └── hybrid/
│
├── policies/                      ← 策略包,本 agent 唯一的核心写权限目录
│   └── <policy_id>/
│
├── contracts/                     ← 只读
│   └── policy_protocol.py
│
├── scenarios/                     ← 只读
│
└── mcp/
    ├── algorithm_library_server.py
    └── simulator_eval_server.py
```

**写权限矩阵**:
- `policies/<policy_id>/` — 完全写权限(本 agent 的产出)
- `algorithms/` — 可写,但只能新增,不能修改已有的 baselines
- `scenarios/`、`evaluator/`、`experiments/` — **绝对禁止写**

---

## 2. AGENTS.md 思路

### 2.1 必须包含的章节

```markdown
# Policy Designer Agent

## Mission
Build a policy package that solves a validated drone scenario while obeying:
- the policy interface defined in contracts/policy_protocol.py
- action bounds from task_spec.yaml
- safety constraints from task_spec.yaml

## Inputs
- scenarios/<task_id>/task_spec.yaml  (read-only, frozen)
- scenarios/<task_id>/model.md
- scenarios/<task_id>/env.py
- contracts/policy_protocol.py
- algorithms/  (existing algorithm library, read-only for baselines)

## Outputs
A policy package `policies/<policy_id>/` containing:
- policy.py                (implements contracts.policy_protocol.Policy)
- train.py                 (CLI signature defined in INTERFACE_2)
- infer.py                 (CLI signature defined in INTERFACE_2)
- default_config.yaml
- search_space.yaml
- algorithm_card.md
- requirements.txt
- tests/
- manifest.json

## Allowed Edits
- algorithms/<new_algorithm>/      (write, new only)
- policies/<policy_id>/            (write)
- policy-specific tests            (write)

## FORBIDDEN Edits
- scenarios/                       (NEVER, including task_spec.yaml)
- evaluator/                       (NEVER, including hidden_tests.py)
- experiments/                     (NEVER)
- contracts/                       (NEVER)
- envs/ (except non-invasive adapters)

## Hard Constraints
1. NEVER modify reward_structure or evaluation_metrics in any task_spec.yaml.
2. NEVER read evaluator/hidden_tests.py contents (only call via API).
3. NEVER bypass action bounds defined in task_spec.action_space.
4. EVERY policy must pass through safety_gate before outputting actions.
5. Raw network output is NOT allowed to directly control the simulator.
6. EVERY trial-time tunable field must be declared in search_space.yaml.

## Algorithm Selection Rule
Prefer the simplest valid method first:
1. geometric rule-based baseline
2. MPC baseline
3. RL baseline (PPO/SAC)
4. multi-agent RL (MAPPO/MADDPG)
5. hybrid: planner + learned residual
6. NEW algorithm code only if existing methods are insufficient AND
   - existing baselines have been benchmarked
   - failure modes are documented
   - new code is restricted to algorithms/<new_name>/

## Required Validation Commands
\```bash
python hooks/post_policy_submit.py --policy policies/<policy_id>
python -m pytest policies/<policy_id>/tests
python scripts/smoke_rollout.py --scenario <task_id> --policy <policy_id>
\```

## Done Definition
A policy is done only when:
- Implements Policy ABC from contracts/policy_protocol.py
- All contract tests pass
- One full rollout runs without error
- algorithm_card.md is complete (all sections filled)
- manifest.json contains freeze_hash
- search_space.yaml fields all appear in get_config_schema() output
```

### 2.2 写 AGENTS.md 的关键

策略 agent 的 AGENTS.md 比场景 agent 更危险,因为它**直接影响实验结果**。三个最重要的红线必须放在最前面、用大写强调:

1. **NEVER 改场景**:任何为了让算法跑高分而调整任务定义的行为都是 reward hacking
2. **NEVER 偷看 hidden tests**:`evaluator/hidden_tests.py` 只能通过 evaluator 接口调用
3. **EVERY 输出过 safety_gate**:学习到的网络不能直接控制仿真器

---

## 3. skills/ 思路

### 3.1 `policy-interface-builder` (核心 skill)

```
.agents/skills/policy-interface-builder/
├── SKILL.md
├── scripts/
│   ├── generate_policy_skeleton.py    ← 根据 task_spec 生成 policy.py 骨架
│   ├── generate_train_script.py       ← 生成符合 §3 命令行签名的 train.py
│   ├── generate_infer_script.py       ← 生成符合 §4 的 infer.py
│   └── validate_interface.py          ← 检查实现是否符合 ABC
├── references/
│   ├── policy_protocol_examples/      ← 已有的实现样例
│   └── action_bound_handling.md
└── templates/
    ├── policy_skeleton.py.tmpl
    ├── train_skeleton.py.tmpl
    └── infer_skeleton.py.tmpl
```

**SKILL.md 要点**:
```markdown
# policy-interface-builder

## When to use
当需要为某个 scenario 生成符合 contracts/policy_protocol.py 的 policy.py 时。
也用于生成 train.py 和 infer.py 的命令行入口。

## What it does
读取 task_spec.yaml → 生成 policy.py 骨架 → 填入算法逻辑 → 校验接口一致性。

## Critical rule
- act() 返回的 action 必须严格在 action_space.[low, high] 范围内
- act() 必须是 pure function: 不 print、不写文件、不修改全局状态
- act() 单次调用 < 50ms (CPU)
- reset(seed) 必须使后续 act 输出 deterministic
```

### 3.2 `algorithm-selector`

根据 scenario 特征选择算法族,输出 `algorithm_plan.md`。

**决策树**(写进 SKILL.md 的 references):

```
任务是单智能体导航 + 动力学简单
  → rule_based + geometric planner

任务有强动力学约束 + 目标几何清晰
  → MPC + safety filter

任务是多智能体对抗 + 完美通信
  → MAPPO with shared critic

任务是多智能体对抗 + 有限通信
  → MAPPO + message encoder + recurrent policy

任务有硬安全约束
  → 任意算法 + CBF-based safety shield

任务规格暗示需要长期规划
  → hybrid: MPC planner + RL residual
```

### 3.3 `mpc-policy-template`

生成 MPC baseline 的标准模板。**适用条件**:
- 动力学模型可被显式建模
- 动作空间是 setpoint 类型 (velocity / acceleration)
- 单步推理时间允许 (>10ms)
- 可解释性是优先项

**输出物**:`policies/<policy_id>/policy.py` 中实现一个调用 CasADi/cvxpy 求解器的 MPC 控制器,封装在 Policy ABC 中。

### 3.4 `mappo-policy-template`

生成 MAPPO 训练模板。**适用条件**:
- 多智能体 + 同步行动 (PettingZoo Parallel API)
- 红蓝对抗 / 自博弈
- 状态/观测可被神经网络处理

**输出物**:
- `policy.py`: 推理时使用的网络
- `train.py`: 实现 centralized training, decentralized execution
- 自带对手采样机制 (`opponent_sampling_ratio` 字段)

### 3.5 `safety-shield-builder`

生成 action validator 和 safety shield。**这是策略 agent 不可省略的一步**——任何学习类策略都必须经过 shield。

```
.agents/skills/safety-shield-builder/
├── SKILL.md
├── scripts/
│   ├── generate_shield.py
│   └── shield_test.py
└── templates/
    └── safety_shield.py.tmpl
```

**Shield 流水线**(写进 SKILL.md):

```
raw_action (from network)
   ↓
schema check (shape, dtype, no NaN/Inf)
   ↓
bound check (clip to [low, high])
   ↓
rate limiter (限制相邻 step 的动作变化率)
   ↓
collision/geofence shield (基于物理预测的安全裁剪)
   ↓
final_action (returned by act())
```

### 3.6 `algorithm-card-writer`

强制生成 `algorithm_card.md`。**避免**: "代码能跑但不知道适用边界"。

模板已在 `INTERFACE_2_POLICY_TO_AUTORESEARCH.md §7` 中定义,本 skill 负责检查每个章节是否非空。

---

## 4. hooks 思路

### 4.1 `pre_policy_submit.py`

**运行时机**: 在 agent 声称"策略写完了"之前,作为软提醒
**职责**: 提示必须的检查项

```python
def main(policy_id):
    checks = [
        check_implements_policy_abc(policy_id),
        check_no_forbidden_imports(policy_id),  # 不能 import scenarios/, evaluator/
        check_safety_shield_present(policy_id),
        check_search_space_consistent(policy_id),
        check_algorithm_card_complete(policy_id),
    ]
    return summarize(checks)
```

### 4.2 `post_policy_submit.py`

**运行时机**: agent 声称完成之后,**强制硬门**
**职责**: 全面校验 + 写入 freeze_hash

```python
def main(policy_id):
    checks = [
        # 接口校验
        check_policy_abc_implementation(policy_id),
        check_get_config_schema_consistency(policy_id),
        
        # 行为校验
        run_smoke_rollout(policy_id, n_episodes=3),
        check_action_bounds_in_random_obs(policy_id, n_samples=1000),
        check_inference_latency(policy_id, threshold_ms=50),
        check_seed_determinism(policy_id),
        
        # 文件校验
        check_train_script_cli(policy_id),       # 验证 --config, --scenario 等参数
        check_infer_script_cli(policy_id),       # 验证产出 eval_results.json schema
        check_algorithm_card_sections(policy_id),
        
        # 红线校验
        check_no_scenario_modifications(),
        check_no_evaluator_modifications(),
        check_no_hidden_test_imports(policy_id),
    ]
    
    if all(c.passed for c in checks):
        write_manifest(policy_id, frozen=True)
        return "frozen"
    return "rejected", failed_checks
```

### 4.3 `safety_gate.py`

**运行时机**: 每次 policy.act() 输出后(运行时被调用)
**职责**: 不可绕过的动作裁剪

```python
def gate(raw_action, env_spec, history):
    # 1. Schema check
    assert raw_action.shape == tuple(env_spec["action_space"]["shape"])
    assert raw_action.dtype == np.float32
    assert not np.any(np.isnan(raw_action))
    assert not np.any(np.isinf(raw_action))
    
    # 2. Bound check (强制裁剪)
    action = np.clip(raw_action, env_spec["action_space"]["low"], 
                                  env_spec["action_space"]["high"])
    
    # 3. Rate limiter
    if history.last_action is not None:
        max_delta = env_spec.get("max_action_delta", 0.5)
        action = np.clip(action, history.last_action - max_delta,
                                  history.last_action + max_delta)
    
    # 4. Geofence shield (任务特定)
    action = apply_geofence_shield(action, history.last_position, env_spec)
    
    return action, {"clipped": not np.allclose(raw_action, action)}
```

**关键**: `safety_gate` 的输出会写入 `info["action_clipped"]`,实验 agent 可以通过 `eval_results.json` 看到裁剪比例,过高即说明策略不健康。

---

## 5. MCP 服务思路 (可选)

### 5.1 `algorithm_library_server.py`

暴露已有算法模块,避免重复造轮子:

- `list_algorithms()` → `["rule_based_ring_nav", "mpc_interceptor", ...]`
- `get_algorithm_metadata(name)` → 返回算法的输入输出、适用场景、计算成本
- `get_algorithm_template(name)` → 返回可复制的代码模板

### 5.2 `simulator_eval_server.py`

提供统一的 rollout 接口(注意:这与 evaluator 不同,evaluator 是最终评测,simulator_eval 用于策略 agent 自己的快速验证):

- `run_rollout(policy_id, scenario_id, seed)` → 返回单 episode 轨迹
- `run_smoke_test(policy_id, scenario_id)` → 快速验证策略不崩溃
- `render_failure_case(run_id)` → 可视化失败 episode

**红线**: 此 MCP 不暴露 hidden_tests 的内容,只暴露 train/val seeds。

---

## 6. 内部工作流程

```
[输入] scenarios/<task_id>/ (冻结)
    ↓
[读取] task_spec.yaml + model.md
    ↓
[skill] algorithm-selector: 决定用哪个算法族
    ↓
[skill] policy-interface-builder: 生成 policy.py 骨架
    ↓
[skill] mpc-policy-template / mappo-policy-template: 填入算法逻辑
    ↓
[skill] safety-shield-builder: 生成 safety shield
    ↓
[skill] algorithm-card-writer: 写 algorithm_card.md
    ↓
[内部] 生成 train.py + infer.py (命令行接口固定)
    ↓
[内部] 生成 default_config.yaml + search_space.yaml
    ↓
[hook] pre_policy_submit.py 软检查
    ↓
[内部] 跑 smoke rollout 自验证
    ↓
[hook] post_policy_submit.py 全面硬门校验
    ↓
[冻结] 写入 manifest.json + freeze_hash
    ↓
[输出] policies/<policy_id>/ 准备好被实验 agent 消费
```

---

## 7. 失败模式与对策

| 失败模式 | 对策 |
|---|---|
| 策略输出动作越界 | `safety_gate.py` 强制裁剪 + `eval_results.action_violation_rate` 监控 |
| 算法选错(简单任务用了复杂方法) | `algorithm-selector` 必须先尝试 rule-based / MPC baseline |
| 算法 agent 偷偷 import scenario 内部状态 | `post_policy_submit.py` 检查 import 白名单 |
| `search_space.yaml` 与实际 config 字段不一致 | `post_policy_submit.py` 验证 `get_config_schema()` 返回值 |
| 推理延迟超标 | `test_inference_latency.py` 警告;若 > 100ms 直接 reject |
| 训练崩溃但未上报 | `train.py` 强制以非零退出码结束 + 实验 agent 监控退出码 |

---

## 8. 与其他 agent 的边界

| 场景 | 场景 agent | **本 agent** | 实验 agent |
|---|:---:|:---:|:---:|
| 写 `policy.py` | ✗ | **✓** | ✗ |
| 改 `task_spec.yaml` | ✓ | ✗ | ✗ |
| 改 `policy.py` 源码 | ✗ | **✓** | ✗ |
| 改 `default_config.yaml` 字段范围 | ✗ | **✓** | ✗ (只能在 search_space 内取值) |
| 写 `algorithm_card.md` | ✗ | **✓** | ✗ |
| 决定 `search_space` 边界 | ✗ | **✓** | ✗ |
| 触发回退到场景 agent | ✗ | **✓** (写 `spec_inconsistency.md`) | ✗ |

**最重要的边界**:
- 上游(场景):本 agent **绝对只读** task_spec。如果觉得 spec 不可解,**只能通过回退路径**写 `spec_inconsistency.md`,不能擅自修改。
- 下游(实验):本 agent 一旦冻结策略包,**绝对不再改源码**。实验 agent 只能修改 config(在 `search_space` 范围内)。如果实验 agent 触发回退,本 agent 才能解冻并升级算法。

---

## 9. "升级回合"机制

当实验 agent 提交 `experiments/<exp_id>/regression_report.md`,触发"算法升级回合":

1. 本 agent 读取 `regression_report.md` (已知失败模式)
2. 决定升级策略:
   - **小升级**: 同一 policy_id 的 minor version,例如增加观测维度、改网络结构
   - **大升级**: 开新 policy_id,切换算法族
3. 完成升级后,**重新走一遍 §6 的完整流程**,产生新版本 policy 包
4. 实验 agent 在新策略上重新跑实验

**关键**: 升级回合不是"在原文件上改",而是产生新版本。旧版本仍然冻结、可追溯。
