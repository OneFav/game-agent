# Game Agent M1 Design

日期：2026-05-11

## 1. 背景与目标

当前仓库包含 5 份 Markdown 规格文档，描述一个面向无人机对抗任务的三 Agent 自动研究系统：

- Scenario Compiler Agent：自然语言任务 → 形式化场景规格。
- Policy Designer Agent：场景规格 → 可运行策略包。
- Experiment AutoResearch Agent：固定策略包 → 小规模实验搜索、最优配置与可复现报告。
- Interface Contract 1：ScenarioSpec 合同。
- Interface Contract 2：PolicyPackage 合同。

M1 目标不是一次性实现完整 RL 科研平台，而是实现一个简化但可运行的三 Agent 垂直切片。系统必须具备真实目录结构、明确合同、校验 hook、CLI 使用入口、端到端产物流，并在根目录输出当前能力说明 `report.md` 与后续任务清单 `task.md`。

## 2. 已确认需求

- 使用入口：CLI。
- 项目本体：三 Agent 架构必须完整落地，包括 `agents/`、`.agents/skills/`、`hooks/`、`contracts/`。
- 依赖策略：轻依赖，仅使用 Python 标准库、`pytest`、`PyYAML`、`numpy`。
- 输入形式：用户自然语言任务描述。
- 自然语言解析：半自由描述；支持更多表达方式，但不追求任意任务泛化。
- 缺失参数处理：尽量使用保守默认值并显式记录到 `assumptions.md`；关键字段无法确认时给出可行动错误。
- Policy Designer：默认生成规则/几何策略，同时提供轻量可训练策略骨架。
- AutoResearch：确定性小规模 sweep，多 seed 评估，生成 leaderboard、best_config 和 report。
- 根目录文档：
  - `report.md`：描述当前项目可解决的任务族、能力与限制。
  - `task.md`：描述剩余任务与后续 roadmap。

## 3. 总体方案

采用“方案 1：M1 垂直切片 + 三 Agent 真实目录”。核心链路为：

```text
用户自然语言任务
  -> Scenario Compiler
  -> scenarios/<task_id>/
  -> Policy Designer
  -> policies/<policy_id>/
  -> AutoResearch
  -> experiments/<exp_id>/
  -> report.md + task.md
```

设计原则：

- KISS：M1 用轻量 numpy 仿真和规则策略跑通合同，不引入真实 RL 栈。
- YAGNI：不实现 MCP、GPU job server、真实多智能体 RL、复杂可视化训练平台。
- DRY：合同字段、路径校验、manifest/hash 逻辑应复用工具函数。
- SOLID：三个 Agent 模块职责清晰，运行期只能写自己的产物目录。

## 4. 目录布局

```text
game-agent/
├─ game_agent/                    # Python 包，CLI 与可复用实现
│  ├─ __init__.py
│  ├─ __main__.py
│  ├─ cli.py
│  ├─ scenario_compiler/
│  ├─ policy_designer/
│  ├─ autoresearch/
│  ├─ envs/drone_ring_game/
│  └─ utils/
├─ agents/
│  ├─ scenario_compiler/
│  │  ├─ AGENTS.md
│  │  ├─ prompt.md
│  │  └─ orchestrator.py
│  ├─ policy_designer/
│  │  ├─ AGENTS.md
│  │  ├─ prompt.md
│  │  └─ orchestrator.py
│  └─ experiment_autoresearch/
│     ├─ AGENTS.md
│     ├─ prompt.md
│     └─ orchestrator.py
├─ .agents/skills/
│  ├─ scenario-spec-compiler/
│  ├─ policy-interface-builder/
│  └─ autoresearch-loop/
├─ contracts/
│  ├─ scenario_schema.yaml
│  └─ policy_protocol.py
├─ hooks/
│  ├─ post_scenario_compile.py
│  ├─ post_policy_submit.py
│  └─ post_experiment_run.py
├─ scenarios/
├─ policies/
├─ experiments/
├─ tests/
├─ pyproject.toml
├─ report.md
└─ task.md
```

边界规则：

- Scenario Compiler 只写 `scenarios/<task_id>/`。
- Policy Designer 只写 `policies/<policy_id>/`，读取 scenario。
- AutoResearch 只写 `experiments/<exp_id>/`，读取 scenario 和 policy。
- `contracts/` 与 `hooks/` 是共享基础设施，不由运行中的三 Agent 任意修改。
- `.agents/skills/` 是能力说明与轻量脚本，不作为用户入口；用户入口是 CLI。

## 5. 数据合同与产物流

### 5.1 ScenarioPackage

由 Scenario Compiler 从自然语言生成：

```text
scenarios/<task_id>/
├─ task_spec.yaml
├─ model.md
├─ env_config.yaml
├─ env.py
├─ assumptions.md
├─ tests/
│  ├─ test_reset_deterministic.py
│  └─ test_obs_action_shape.py
└─ manifest.json
```

`task_spec.yaml` 最小字段：

- `schema_version`
- `task_id`
- `task_family: drone_ring_game`
- `formalism`
- `agents`
- `observation_space`
- `action_space`
- `reward_structure`
- `evaluation_metrics`
- `termination_conditions`
- `splits`

约束：

- `reward_structure` 与 `evaluation_metrics` 必须分离。
- `evaluation_metrics.primary` 有且仅有一个主指标。
- `hard_constraints` 至少包含 `collision_rate`。
- 缺失自然语言参数必须写入 `assumptions.md`。
- 关键字段不能静默假设，尤其是通信模式、智能体数量、时间上限。

### 5.2 PolicyPackage

由 Policy Designer 读取 ScenarioPackage 生成：

```text
policies/<policy_id>/
├─ policy.py
├─ train.py
├─ infer.py
├─ default_config.yaml
├─ search_space.yaml
├─ algorithm_card.md
├─ requirements.txt
├─ tests/
│  ├─ test_policy_interface.py
│  └─ test_action_bounds.py
└─ manifest.json
```

M1 默认策略：

- `RuleRingNavigationPolicy`。
- 使用几何规则控制无人机朝目标或圆环方向运动。
- action 必须裁剪到 `task_spec.action_space`。
- `reset(seed)` 后行为确定。
- 提供轻量可训练策略骨架，但不阻塞主链路。

### 5.3 ExperimentPackage

由 AutoResearch 执行确定性 sweep 生成：

```text
experiments/<exp_id>/
├─ trials/
│  ├─ trial_0001/
│  │  ├─ config.yaml
│  │  ├─ metrics.json
│  │  └─ log.json
│  └─ trial_0002/
├─ leaderboard.csv
├─ best_config.yaml
├─ report.md
└─ manifest.json
```

AutoResearch 只消费：

- scenario 的 `evaluation_metrics`、`splits` 和环境接口。
- policy 的 `search_space.yaml`、`infer.py` 或 `Policy` 接口。

AutoResearch 不读取或修改 reward 作为晋级标准，以降低 reward hacking 风险。

## 6. CLI 设计

### 6.1 主链路命令

```bash
python -m game_agent run \
  --task "设计一个红蓝无人机穿环对抗任务，红方穿过圆环，蓝方追击拦截，通信有延迟" \
  --task-id drone_ring_001 \
  --policy-id rule_ring_nav_v1 \
  --exp-id exp_drone_ring_001
```

执行顺序：

1. `ScenarioCompiler.compile(task_text, task_id, output_dir)`
   - 解析自然语言。
   - 生成 `scenarios/<task_id>/`。
   - 调用 `hooks/post_scenario_compile.py` 校验。
2. `PolicyDesigner.build(scenario_dir, policy_id, output_dir)`
   - 读取 `task_spec.yaml`。
   - 生成 `policies/<policy_id>/`。
   - 调用 `hooks/post_policy_submit.py` 校验。
3. `AutoResearch.run(scenario_dir, policy_dir, exp_id, output_dir)`
   - 读取 scenario + policy。
   - 基于 `search_space.yaml` 做小规模 sweep。
   - 多 seed 评估。
   - 生成实验产物。
   - 调用 `hooks/post_experiment_run.py` 校验。
4. 写或更新根目录 `report.md` 与 `task.md`。

### 6.2 分步命令

```bash
python -m game_agent compile-scenario --task "红方无人机穿过圆环，蓝方追击拦截，通信有延迟" --task-id drone_ring_001

python -m game_agent build-policy \
  --scenario scenarios/drone_ring_001 \
  --policy-id rule_ring_nav_v1

python -m game_agent run-experiment \
  --scenario scenarios/drone_ring_001 \
  --policy policies/rule_ring_nav_v1 \
  --exp-id exp_drone_ring_001
```

CLI 行为：

- 不做复杂交互。
- 参数缺失时给清晰错误。
- 默认拒绝覆盖已存在产物目录；M1 不默认实现 `--overwrite`。
- 解析失败时输出可行动错误，不生成半成品。

## 7. 核心模块设计

### 7.1 `game_agent.scenario_compiler`

职责：把半自由自然语言任务编译成 ScenarioPackage。

M1 边界：

- 支持 `drone_ring_game` 任务族。
- 支持识别关键词：无人机、红蓝、追击、拦截、穿环、圆环、通信延迟、丢包、局部观测、超时。
- 支持抽取简单数值：智能体数量、圆环数量、时间步上限、通信延迟。
- 不能识别的参数使用保守默认值并写入 `assumptions.md`。
- 不修改 policy、experiment、contract。

### 7.2 `game_agent.policy_designer`

职责：读取 ScenarioPackage，生成 PolicyPackage。

M1 边界：

- 默认生成 `RuleRingNavigationPolicy`。
- action 严格裁剪到 bounds。
- 支持少量可调参数：`speed_scale`、`intercept_gain`、`safety_margin`。
- 提供 `train.py` 骨架。
- 不修改 scenario、contracts、experiments。

### 7.3 `game_agent.autoresearch`

职责：读取 scenario + policy，执行确定性 sweep。

M1 边界：

- 读取 `search_space.yaml`。
- 对小规模参数网格做多 seed 评估。
- 指标包括 `success_rate`、`collision_rate`、`out_of_bounds_rate`、`avg_episode_length`。
- 根据 `evaluation_metrics.primary` 与 hard constraints 选出 best config。
- 生成 leaderboard、best_config、report、manifest。
- 不修改 policy 源码，不读取 reward 作为 promotion 标准。

### 7.4 `game_agent.envs.drone_ring_game`

M1 环境是轻量 numpy 仿真：

- 使用简化 2D 内核，对外保持固定 observation/action shape。
- red 目标是依次穿过圆环。
- blue 追击 red。
- 终止条件：全部穿环、碰撞、越界、timeout。
- `reset(seed)` 确定性。
- 不模拟高保真动力学，只保留验证策略与实验循环所需行为。

## 8. 校验与测试

### 8.1 Hook

```text
hooks/post_scenario_compile.py
hooks/post_policy_submit.py
hooks/post_experiment_run.py
```

`post_scenario_compile.py`：

- 检查 `scenarios/<task_id>/` 必需文件齐全。
- 校验 `task_spec.yaml` 必需字段。
- 验证 reward 与 evaluation metrics 分离。
- 验证 `env.py` 可导入，reset deterministic。

`post_policy_submit.py`：

- 检查 policy 包必需文件齐全。
- 验证 `policy.py` 实现 `Policy` 协议。
- 验证 action shape/bounds。
- 验证 `search_space.yaml` 字段能被实验使用。

`post_experiment_run.py`：

- 检查 `leaderboard.csv`、`best_config.yaml`、`report.md`、`manifest.json`。
- 检查每个 trial 有 `config.yaml`、`metrics.json`、`log.json`。
- 检查 best config 能对应 leaderboard 中最优 trial。

### 8.2 测试

```text
tests/
├─ test_cli_smoke.py
├─ test_scenario_compiler.py
├─ test_policy_designer.py
├─ test_autoresearch.py
└─ test_hooks.py
```

测试聚焦合同可执行与端到端冒烟，不追求高保真仿真验证。

## 9. 错误处理

错误分三类：

- 用户输入错误：任务族无法识别、task-id 非法、路径不存在。返回清晰提示，不生成半成品。
- 合同错误：缺字段、shape 不一致、action 越界。hook fail，并说明具体文件和字段。
- 运行错误：trial 失败、policy infer 异常。记录到 trial `log.json`，AutoResearch 继续或终止，不能静默吞错。

## 10. 根目录报告与任务清单

### 10.1 `report.md`

`report.md` 是项目能力说明报告，不是单次实验报告。内容包括：

- 当前项目版本与 M1 能力概述。
- 支持的任务族：简化无人机穿环、追逃、拦截类 `drone_ring_game`。
- 可识别的自然语言任务描述范围。
- 可生成的 scenario、policy、experiment 产物。
- 当前不支持的任务族与限制。
- 下一步扩展建议，并引用 `task.md`。

必须明确说明：当前项目不是通用无人机仿真平台，也不是完整 RL 研究框架。

### 10.2 `task.md`

`task.md` 记录剩余任务与 roadmap。建议分组：

- 高保真环境与 PettingZoo/Gymnasium 接入。
- 更强自然语言解析。
- 真正 RL 策略与训练管线。
- MCP 服务与 artifact store。
- 更完整的合同测试与 hidden evaluator。
- 多任务族扩展。

## 11. 范围外内容

M1 不实现：

- 真实 MAPPO/MADDPG/PPO/SAC 训练。
- GPU 作业调度。
- MCP server。
- 高保真无人机动力学。
- 可视化 dashboard。
- 多任务族泛化。
- hidden tests/evaluator 安全隔离。
- 自动 git commit/push。

## 12. 验收标准

M1 完成后应满足：

1. `python -m game_agent run --task "红方无人机穿过圆环，蓝方追击拦截，通信有延迟" --task-id drone_ring_001 --policy-id rule_ring_nav_v1 --exp-id exp_drone_ring_001` 能端到端生成 scenario、policy、experiment、root report 与 task 清单。
2. 三 Agent 的目录、AGENTS.md、prompt、orchestrator 存在且边界清晰。
3. `.agents/skills/` 中至少包含三个核心 skill 说明。
4. `contracts/` 与 `hooks/` 可被 CLI 和 tests 使用。
5. `pytest` 通过。
6. 生成的 `report.md` 明确当前支持任务族与限制。
7. 生成的 `task.md` 明确剩余任务。
