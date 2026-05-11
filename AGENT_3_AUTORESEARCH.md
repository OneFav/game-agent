# Experiment AutoResearch Agent — 仓库架构与功能

> **角色定位**: 固定 policy 包 → 最优配置 + 可复现研究报告的**自动科研循环**
> **负责人**: 你
> **核心红线**: 优化解法,不偷换评价标准。不能改算法源码,不能改场景,不能改 evaluator。

---

## 0. 一句话职责

把一个**冻结的策略包**当作黑盒,在固定场景上反复运行 9 步 trial 循环,产出**带假设、带诊断、带回退建议**的科研报告——而不是简单的 hyperparameter sweep。

**这是整个系统抗 reward hacking 的最后一道防线**,因为本 agent **唯一被允许修改的文件类型是 `experiments/<exp_id>/` 下的产物**。

---

## 1. 在仓库中的位置

```
auto_drone_research/
├── agents/
│   └── experiment_autoresearch/
│       ├── AGENTS.md              ← 本 agent 的运行规则
│       ├── prompt.md              ← 系统提示词
│       └── orchestrator.py        ← 9 步循环的编排器
│
├── .agents/skills/                ← 共享技能,本 agent 主要使用 5 个
│   ├── autoresearch-loop/
│   ├── sweep-space-builder/
│   ├── metrics-analyzer/
│   ├── failure-replay/
│   └── ablation-report-writer/
│
├── hooks/
│   ├── pre_experiment_run.py
│   ├── post_experiment_run.py
│   └── promotion_gate.py
│
├── experiments/                   ← 本 agent 唯一的核心写权限目录
│   └── <exp_id>/
│       ├── trials/
│       │   ├── trial_0001/
│       │   ├── trial_0002/
│       │   └── ...
│       ├── leaderboard.csv
│       ├── best_config.yaml
│       ├── best_checkpoint.pt
│       ├── failure_cases/
│       ├── report.md
│       └── regression_report.md   ← 触发回退时产生
│
├── policies/                      ← 只读
├── scenarios/                     ← 只读
├── evaluator/                     ← 只读 (但可以调用其接口)
│
└── mcp/
    ├── experiment_tracker_server.py
    ├── artifact_store_server.py
    └── gpu_job_server.py          ← 可选,用于远程训练
```

**写权限矩阵**(强约束):
- `experiments/<exp_id>/` — 完全写权限(本 agent 的产出)
- `policies/`、`scenarios/`、`evaluator/`、`algorithms/`、`contracts/`、`hooks/`、`envs/` — **绝对禁止写**

如果本 agent 哪怕修改了 `policy.py` 一个字符,整个系统的可信度就崩了。

---

## 2. AGENTS.md 思路

### 2.1 必须包含的章节

```markdown
# Experiment AutoResearch Agent

## Mission
Run reproducible experiments to optimize a fixed policy package on fixed scenario benchmarks.
Produce hypothesis-driven trial records, leaderboards, failure analyses, and rollback signals.

## Inputs
- scenarios/<task_id>/                  (read-only, frozen)
- policies/<policy_id>/                 (read-only, frozen)
- policies/<policy_id>/search_space.yaml
- experiment_budget (max_trials, seeds_per_trial, wall_time)

## Outputs
- experiments/<exp_id>/trials/<trial_id>/
    config.yaml
    seed
    training_log.json
    eval_results.json
    failure_traces/
    diagnosis.md                        (每个 trial 的假设和诊断)
- experiments/<exp_id>/leaderboard.csv
- experiments/<exp_id>/best_config.yaml
- experiments/<exp_id>/best_checkpoint.pt
- experiments/<exp_id>/report.md
- experiments/<exp_id>/regression_report.md   (触发回退时)

## Allowed Edits
- experiments/                          (write)
- experiments/<exp_id>/                 (write)
- analysis notebooks (in experiments/<exp_id>/)

## FORBIDDEN Edits
- scenarios/                            (NEVER, even task_spec.yaml)
- policies/                             (NEVER, even default_config.yaml)
- algorithms/                           (NEVER)
- evaluator/                            (NEVER)
- contracts/                            (NEVER)
- hooks/                                (NEVER)
- envs/                                 (NEVER)

## Hard Constraints
1. NEVER modify policy source code. Tune ONLY via config.
2. NEVER modify config fields outside search_space.yaml.
3. NEVER read evaluator/hidden_tests.py contents.
4. NEVER use hidden_test results to guide trial decisions (only for final report).
5. EVERY trial must record: hypothesis, change, result, diagnosis, next.
6. EVERY promotion to "best" must satisfy:
   - All hard_constraints passed
   - Cross-seed stability verified (>=3 seeds)
   - No regression on stress tests
7. NEVER report a result without seed, config, commit hash, and metric file.

## Experiment Loop (9 Steps)
For every trial:
1. Read current best result and failure modes
2. Diagnose what's blocking progress
3. State a hypothesis (in plain English)
4. Modify ONLY declared search_space parameters
5. Run training (call policy/train.py via subprocess)
6. Run fixed evaluation (call policy/infer.py via subprocess)
7. Log all metrics and compare to baseline
8. Update leaderboard
9. Decide: continue / promote / rollback

## Rollback Rule
After N consecutive trials below SLA threshold:
- Write experiments/<exp_id>/regression_report.md
- Document: search space exhausted, failure modes, recommendations
- HALT this experiment. Do NOT continue tuning.
- Hand off to Policy Designer Agent.

## Required Validation Commands
\```bash
python hooks/pre_experiment_run.py --exp <exp_id>
python hooks/promotion_gate.py --trial <trial_id>
python hooks/post_experiment_run.py --exp <exp_id>
\```

## Done Definition
An experiment is done only when:
- Budget exhausted OR rollback triggered OR target met
- All trial directories complete (config + log + metrics)
- leaderboard.csv finalized
- report.md written
- best_checkpoint.pt promoted (if applicable)
- No file outside experiments/<exp_id>/ has been modified
```

### 2.2 写 AGENTS.md 的关键

本 agent 的 AGENTS.md 是**反 reward hacking 的核心文档**。三条最关键的红线必须用大写强调:

1. **NEVER 改源码**:策略包的所有文件本 agent 都是只读的
2. **EVERY trial 写假设**:这是和普通 hyperparameter sweep 的根本区别
3. **EVERY promotion 跨 seed 验证**:单 seed 高分不算赢

---

## 3. skills/ 思路

### 3.1 `autoresearch-loop` (核心 skill)

这是本 agent 的灵魂,实现 Karpathy-style 自动科研循环。

```
.agents/skills/autoresearch-loop/
├── SKILL.md
├── scripts/
│   ├── propose_hypothesis.py    ← 基于历史 trial 生成下一个假设
│   ├── run_trial.py             ← 9 步循环的单 trial 执行
│   ├── diagnose_failure.py      ← 失败模式分类
│   └── decide_next.py           ← 继续 / 晋级 / 回退决策
├── references/
│   ├── hypothesis_taxonomy.md   ← 常见假设类型分类
│   ├── failure_mode_catalog.md  ← 已知失败模式目录
│   └── karpathy_autoresearch.md ← 参考资料
└── templates/
    └── diagnosis_md.tmpl
```

**SKILL.md 要点**:

```markdown
# autoresearch-loop

## When to use
Always — this is the main inner loop of AutoResearch agent.

## What it does
Implements the 9-step hypothesis-driven loop:

1. Read leaderboard.csv → identify best so far + plateau pattern
2. Read recent failure_cases/ → identify dominant failure mode  
3. Write hypothesis (plain English, why this change might help)
4. Modify config (only fields in search_space.yaml)
5. Run training (subprocess call to policy/train.py)
6. Run evaluation (subprocess call to policy/infer.py)
7. Compare to baseline (statistical test if cross-seed)
8. Update leaderboard.csv
9. Decide:
   - improvement & passes promotion gate → mark as new best
   - no improvement, budget remains → next hypothesis
   - N consecutive failures → trigger rollback

## Required output per trial
trial_<id>/diagnosis.md MUST contain:
- Hypothesis: <one sentence>
- Change: <param: from X to Y>
- Expected: <what should happen>
- Result: <actual numbers>
- Diagnosis: <why result matched/didn't match expectation>
- Next: <what to try next OR rollback signal>

## Critical rule
This skill is what makes the system "research" rather than "sweep".
NEVER skip writing the hypothesis. NEVER write hypothesis after seeing the result.
```

### 3.2 `sweep-space-builder`

根据策略 agent 提供的 `search_space.yaml`,在每个 trial 中**有原则地**采样,而不是简单的 grid / random。

```
.agents/skills/sweep-space-builder/
├── SKILL.md
└── scripts/
    ├── sample_from_priors.py    ← 基于策略 agent 的 priority_1 / priority_2 采样
    ├── bayesian_optimize.py     ← BO 加速搜索 (可选)
    └── validate_config.py       ← 确保采样值在 search_space 范围内
```

**关键约束**: 本 skill **只能在 `search_space.yaml` 声明的字段中采样**。如果想试一个未声明的字段(如改网络层数),必须**回退**到策略 agent。

### 3.3 `metrics-analyzer`

分析 `metrics.jsonl` 和 `leaderboard.csv`,输出统计判断。

```
.agents/skills/metrics-analyzer/
├── SKILL.md
└── scripts/
    ├── compute_cross_seed_stats.py  ← 跨 seed 均值/方差/CI
    ├── detect_plateau.py             ← 检测训练曲线是否进入平台期
    ├── compare_to_baseline.py        ← 与 baseline 的统计差异检验
    └── stress_test_regression.py     ← stress test 上是否退化
```

**关键能力**:
- **跨 seed 稳定性**: 同一 config 至少 3 个 seed,方差超过阈值 → 不算 promotion
- **统计显著性**: 用 t-test / bootstrap CI,而不是单点比较
- **平台期检测**: 连续 N 个 trial 主指标无显著提升 → 触发回退

### 3.4 `failure-replay`

重放失败 episode,分类失败模式。这是回退报告的关键依据。

```
.agents/skills/failure-replay/
├── SKILL.md
├── scripts/
│   ├── replay_episode.py         ← 用 checkpoint 重跑某个 seed
│   ├── classify_failure.py       ← 失败模式分类(基于 info 字段 + 轨迹)
│   └── render_failure_video.py
└── references/
    └── failure_mode_taxonomy.md
```

**预定义失败类别**(写进 references):
- `collision_with_opponent`: 与对手碰撞
- `out_of_bounds`: 越界
- `ring_approach_hesitation`: 圆环前犹豫
- `oscillation`: 控制震荡
- `comm_blackout_loss`: 通信中断后失控
- `adversarial_blocking`: 被对手成功拦截
- `unknown`: 未分类(需要人工诊断)

### 3.5 `ablation-report-writer`

生成最终 `report.md`。**强制章节**:

```markdown
# Experiment Report: <exp_id>

## Summary
<one paragraph: best metric, n_trials, key findings>

## Setup
- Scenario: <task_id> (freeze_hash)
- Policy: <policy_id> (freeze_hash)
- Search space: <which fields>
- Budget: <n_trials × n_seeds × max_steps>

## Best Configuration
- config: <yaml block>
- metrics: <table with primary + secondary + hard_constraints>
- cross-seed CI: <numbers>

## Trial Trajectory
- <n_trials in chronological order>
- key inflection points (when did best metric jump?)

## Ablations
<systematic ablation of top-3 most impactful hyperparameters>

## Failure Analysis
<dominant failure modes from failure_cases/, with example replay videos>

## Stress Test Results
<table: stress_test_name × primary_metric>

## Hidden Test Result
<single number, computed only ONCE at the end>

## Reproducibility Manifest
- code commit: <git sha>
- requirements.txt hash: <sha>
- random seeds used: <list>

## Recommendations
<what to try next: more trials? different algorithm? rollback?>
```

---

## 4. hooks 思路

### 4.1 `pre_experiment_run.py`

**运行时机**: 实验启动前
**职责**: 确保起跑线干净

```python
def main(exp_id, policy_id, scenario_id):
    checks = [
        # 上游冻结
        check_scenario_frozen(scenario_id),       # manifest.frozen_at != null
        check_policy_frozen(policy_id),
        check_freeze_hashes_match(scenario_id, policy_id),
        
        # 配置合法
        check_search_space_valid(policy_id),
        check_search_space_subset_of_config_schema(policy_id),
        check_budget_configured(exp_id),
        
        # 输出准备
        check_exp_dir_unique(exp_id),             # 不能覆盖已有实验
        check_disk_space(min_gb=50),
        
        # 红线检查
        check_no_modifications_to_policy(policy_id),
        check_no_modifications_to_scenario(scenario_id),
    ]
    
    if not all(c.passed for c in checks):
        return "blocked", failed_checks
    return "ok"
```

### 4.2 `promotion_gate.py`

**运行时机**: 每次 trial 评测完之后
**职责**: 不可绕过的"晋级硬门"

```python
def evaluate(trial_results, current_best, scenario_metrics_schema):
    # 1. 硬约束必须全部通过
    for constraint in scenario_metrics_schema["hard_constraints"]:
        actual = trial_results["metrics"]["hard_constraints"][constraint["name"]]
        if not actual["passed"]:
            return PromotionDecision.REJECTED, f"hard constraint {constraint['name']} failed"
    
    # 2. 主指标必须改进 (统计显著)
    primary = trial_results["metrics"]["primary"]
    if current_best is not None:
        improvement = primary["value"] - current_best["primary"]["value"]
        if improvement < SIGNIFICANCE_THRESHOLD:
            return PromotionDecision.NO_IMPROVEMENT, "primary metric not significantly improved"
    
    # 3. 跨 seed 稳定性 (必须至少 3 个 seed)
    if len(trial_results["per_seed_metrics"]) < 3:
        return PromotionDecision.INSUFFICIENT_SEEDS, "need >=3 seeds for promotion"
    
    cross_seed_std = np.std([m["primary"] for m in trial_results["per_seed_metrics"]])
    if cross_seed_std > MAX_ACCEPTABLE_STD:
        return PromotionDecision.UNSTABLE, "high cross-seed variance"
    
    # 4. Stress test 不严重退化
    for st_name, st_result in trial_results["metrics"]["stress_tests"].items():
        if current_best and st_result["primary"] < current_best["stress_tests"][st_name] - 0.1:
            return PromotionDecision.STRESS_REGRESSION, f"regressed on {st_name}"
    
    return PromotionDecision.PROMOTED
```

### 4.3 `post_experiment_run.py`

**运行时机**: 实验结束后
**职责**: 完整性 + 不可篡改性校验

```python
def main(exp_id):
    checks = [
        # 完整性
        check_all_trials_have_config(exp_id),
        check_all_trials_have_metrics(exp_id),
        check_leaderboard_consistent_with_trials(exp_id),
        check_best_checkpoint_exists(exp_id) if has_promoted(exp_id) else True,
        check_report_md_complete(exp_id),
        
        # 红线
        check_no_modifications_outside_exp(exp_id),
        check_no_evaluator_modifications(),
        check_no_policy_source_modifications(),
        check_no_scenario_modifications(),
        
        # 可复现性
        check_all_seeds_recorded(exp_id),
        check_git_commit_recorded(exp_id),
        check_freeze_hashes_recorded(exp_id),
    ]
    
    if all(c.passed for c in checks):
        write_exp_manifest(exp_id, finalized=True)
        return "finalized"
    return "rejected", failed_checks
```

---

## 5. MCP 服务思路

本 agent 是最受益于 MCP 的——因为它要管理大量实验 artifact。

### 5.1 `experiment_tracker_server.py` (推荐第一版就上)

```
工具列表:
  create_experiment(policy_id, scenario_id, budget) → exp_id
  log_trial(exp_id, trial_id, config, metrics)
  get_leaderboard(exp_id) → DataFrame
  compare_trials(trial_ids) → comparison report
  get_best_config(exp_id) → yaml
  promote_best(exp_id, trial_id)
  query_history(policy_id, scenario_id) → 跨实验查询
```

**价值**: agent 不用手动管理文件夹结构,通过统一 API 访问所有历史。

### 5.2 `artifact_store_server.py`

```
工具列表:
  save_checkpoint(trial_id, path)
  load_checkpoint(trial_id)
  save_failure_trace(trial_id, episode_id, trajectory)
  save_render_video(trial_id, episode_id, video_bytes)
  cleanup_failed_trials(exp_id, keep_top_n=10)
```

**价值**: 实验产物可以集中管理,不至于把仓库撑爆。

### 5.3 `gpu_job_server.py` (可选,远程训练)

```
工具列表:
  submit_train_job(config, scenario, policy) → job_id
  check_job_status(job_id)
  collect_metrics(job_id)
  kill_job(job_id)
```

**白名单约束**: 此 MCP 必须严格限制可执行命令,只允许 `python policies/<id>/train.py ...` 形式的调用,禁止任意 shell 命令。

---

## 6. 内部工作流程 (9 步循环)

```
[输入] policies/<policy_id>/ + scenarios/<task_id>/
    ↓
[hook] pre_experiment_run.py 校验冻结状态
    ↓
[初始化] 创建 experiments/<exp_id>/ 目录
    ↓
┌─────────────────────────────────┐
│  9 步 Trial 循环 (重复)          │
│                                 │
│  ① Hypothesis (写假设)           │
│      ↓                          │
│  ② Modify Config                │
│      ↓                          │
│  ③ Train (subprocess train.py)  │
│      ↓                          │
│  ④ Fixed Evaluation             │
│      ↓                          │
│  ⑤ Hard Constraint Check        │
│      ↓                          │
│  ⑥ Log Metrics                  │
│      ↓                          │
│  ⑦ Compare Baseline             │
│      ↓                          │
│  ⑧ Update Leaderboard           │
│      ↓                          │
│  ⑨ Diagnose & Decide Next       │
│                                 │
│   出口 1 (绿色): 通过晋级门      │
│       → 写入 best_checkpoint    │
│       → 进入下一轮迭代          │
│                                 │
│   出口 2 (黄色): 未通过但有预算  │
│       → 回到 ① 提下一个假设      │
│                                 │
│   出口 3 (红色): 连续 N 轮失败   │
│       → 触发跨阶段回退          │
│       → 跳出循环                │
└─────────────────────────────────┘
    ↓
[skill] ablation-report-writer 生成 report.md
    ↓
[最终评测] 在 hidden_test 上跑一次最终模型 (只跑这一次)
    ↓
[hook] post_experiment_run.py 完整性校验
    ↓
[输出] experiments/<exp_id>/ 完整产出
```

---

## 7. 三种出口的具体定义

### 7.1 绿色出口:promotion (来自 ⑦ Compare Baseline)

**触发条件**:
- 主指标统计显著优于当前 best
- 所有 hard_constraints 通过
- 跨 seed 方差 < 阈值
- Stress test 没有严重退化

**动作**:
- 复制 `checkpoint_final.pt` 到 `experiments/<exp_id>/best_checkpoint.pt`
- 更新 `best_config.yaml`
- 在 `leaderboard.csv` 中标记 `promoted=true`

### 7.2 黄色出口:continue (来自 ⑤ Hard Constraint Check)

**触发条件**:
- 未通过 promotion gate
- 但仍在 trial budget 内
- 最近 N 轮的失败模式有变化(说明搜索还在探索)

**动作**:
- 记录到 `leaderboard.csv` 但不晋级
- `propose_hypothesis.py` 基于本次失败提出新假设
- 进入下一轮 trial

### 7.3 红色出口:rollback (来自 ⑨ Diagnose)

**触发条件**(任一即触发):
- 连续 N 轮(默认 N=10)主指标无显著提升 + 失败模式相同
- 当前 best 远低于策略 agent 在 manifest 中声明的 `expected_primary_metric`
- Trial budget 耗尽且未达 SLA

**动作**:
1. **停止实验循环**(不再启动新 trial)
2. 写 `experiments/<exp_id>/regression_report.md`(模板见 §8)
3. 通知策略 agent(写一个 marker 文件 `pending_rollback.flag`)
4. 仍然完成 `report.md` 和 `post_experiment_run.py`

---

## 8. 回退报告模板 (`regression_report.md`)

```markdown
# Regression Report — <exp_id>

## Trigger
- Triggered after: <N> trials
- Best primary metric achieved: <value> (threshold: <target>)
- Trend: <plateau / oscillation / divergence>

## Search Space Coverage
| Parameter | Range Tested | Best Value | Notes |
|---|---|---|---|
| learning_rate | [1e-5, 1e-3] | 5e-4 | 已扫遍,无突破 |
| safety_penalty | [-100, -1] | -10 | 增大反而降低 success_rate |
| ... | ... | ... | ... |

## Dominant Failure Mode
- Type: ring_approach_hesitation
- Frequency: 70% of failed episodes
- Description: <one paragraph>
- Replay: failure_cases/seed_105_ep_3.mp4

## Hypothesis on Why
- 推测 1: 观测维度不足以分辨 ring 朝向
- 推测 2: reward shaping 导致策略过于保守
- 推测 3: <other>

## Recommendation to Policy Designer
- [ ] 是否考虑加入 LSTM / attention 处理历史观测
- [ ] 是否考虑改算法族 (MAPPO → MAT)
- [ ] 是否需要对手课程化训练
- [ ] 当前算法卡参考: policies/<policy_id>/algorithm_card.md

## What I Will NOT Do
- 不擅自改 policy.py 代码
- 不擅自改 task_spec
- 不擅自扩展 search_space (那需要策略 agent 重新声明)

## Handoff
- Marker file: experiments/<exp_id>/pending_rollback.flag
- All trial data preserved in experiments/<exp_id>/
- Awaiting Policy Designer to produce a new policy version
```

---

## 9. 失败模式与对策

| 失败模式 | 对策 |
|---|---|
| 单 seed 偶然高分被误认为 best | `promotion_gate.py` 强制至少 3 个 seed |
| 训练崩溃但被忽略 | `train.py` 退出码非零 → trial 标记 failed,不进 leaderboard |
| 偷偷扩展 search space | `pre_experiment_run.py` 校验配置字段全在 search_space 内 |
| 用 hidden_test 指导 trial 决策 | hidden_test 只在 `report.md` 生成时调用一次,且结果不进 leaderboard |
| 失败 episode 没保存导致无法诊断 | `failure-replay` skill 强制保存所有 failed episode 的轨迹 |
| Stress test 退化未发现 | `promotion_gate.py` 检查每个 stress test 的 regression |
| 实验产物超出磁盘 | `artifact_store_server.cleanup_failed_trials` 自动清理 |

---

## 10. 与其他 agent 的边界

| 场景 | 场景 agent | 策略 agent | **本 agent** |
|---|:---:|:---:|:---:|
| 写 `policy.py` | ✗ | ✓ | ✗ |
| 改 `default_config.yaml` 字段范围 | ✗ | ✓ | ✗ |
| 在 `search_space` 范围内取值 | ✗ | ✗ | **✓** |
| 写 `experiments/<exp_id>/` | ✗ | ✗ | **✓** |
| 调用 evaluator 接口 | ✗ | ✗ (只在自测时) | **✓** |
| 触发回退到策略 agent | ✗ | ✗ | **✓** (`regression_report.md`) |
| 修改 task_spec | ✓ | ✗ | ✗ |

**最重要的边界**:
- 上游(策略):本 agent 收到的策略包是**绝对的黑盒**。任何想要"改源码"的冲动,都必须转化为回退报告。
- 评测器(evaluator):本 agent **只能调用 evaluator 接口**,不能读其内部实现(尤其是 hidden_tests)。
- 下游(谁?):本 agent 的下游是**人类研究者**——你的老师会读 `report.md`,所以这份报告必须可信、可复现、可质疑。

---

## 11. 为什么这个 agent 是反 reward hacking 的最后防线

整个系统的 reward hacking 风险来自三个方向:
1. 场景 agent 把任务定得太好做(太宽松的 evaluation)— 由 evaluator 硬门挡住
2. 策略 agent 把代码写得太"巧"(直接读取 env 内部状态)— 由 `safety_gate` 和 import 检查挡住
3. **实验 agent 偷偷调整测量过程** — 这是最隐蔽的风险,只能靠**写权限收紧 + hidden test + 跨 seed 验证**来防

本 agent 的 AGENTS.md 要让老师一眼就能看出:**这个 agent 没有任何作弊空间**——它只能修改 `experiments/`,只能在 `search_space` 范围内取值,只能在最后调用一次 `hidden_test`。

这是为什么"AutoResearch 适合独立开发"的根本原因:它的接口收敛、行为可审计,你可以闭门写完后,通过 `post_experiment_run.py` 这一个 hook 完成全部正确性验证。

---

## 12. M1 联调清单(实验 agent 视角)

第一周末必须验证的最简版本:

- [ ] 朋友交付一个 mock 场景(可以是手写的 `task_spec.yaml`)+ 一个 `RandomPolicy`(act 返回随机动作)
- [ ] 你的 AutoResearch 能完成完整的一个 trial:
  - [ ] 读取 freeze_hash 验证场景/策略已冻结
  - [ ] 生成一份 `config.yaml` 写入 `trials/trial_0001/`
  - [ ] 调用 `train.py` (即使训练只有 100 步也行)
  - [ ] 调用 `infer.py` 产出 `eval_results.json`
  - [ ] 解析结果写入 `leaderboard.csv`
  - [ ] 写一份(空内容也行的)`diagnosis.md`
  - [ ] `post_experiment_run.py` 全部检查通过
- [ ] 验证回退路径:故意构造一个不可解的 mock 场景,确认你的 agent 在 N 轮后正确产出 `regression_report.md`

通过这个 M1 之后,后续都是数据质量和算法选择的事,而不是接口对接的事——**接口已经稳定**。
