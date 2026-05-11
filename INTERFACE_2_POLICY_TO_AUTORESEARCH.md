# Interface Contract 2: PolicyPackage
## 策略设计 Agent → 自动实验 Agent

> **本文档是合同,不是文档。** 这是整个项目最关键的接口——你的朋友闭门写策略,你闭门写实验,最后能不能对上全靠这份文档。

---

## 0. 这份合同管什么

**生产方**:策略设计 Agent (Policy Designer) — 朋友负责
**消费方**:自动实验 Agent (AutoResearch) — 你负责
**生命周期**:策略 agent 完成 → `post_policy_submit` 校验 → 冻结 policy 源码 → 实验 agent 反复调用 (只改 config)

> **核心原则**:实验 agent **只通过文件和命令行**与策略代码交互,不依赖任何"我们当面对过的隐含约定"。任何你需要的信息必须在合同中显式写明。

---

## 1. 物理交付物 (Deliverables)

每个策略包以**目录**形式交付,目录名 = `policy_id`。

```
policies/<policy_id>/
├── policy.py               [必需] 实现 contracts/policy_protocol.py 中的 Policy ABC
├── train.py                [必需] 训练入口,命令行接口固定
├── infer.py                [必需] 推理评测入口,命令行接口固定
├── default_config.yaml     [必需] 默认超参,实验 agent 在此基础上修改
├── search_space.yaml       [必需] 推荐搜索空间(策略 agent 给实验 agent 的提示)
├── algorithm_card.md       [必需] 算法说明,实验 agent 写报告时引用
├── requirements.txt        [必需] 依赖锁定 (建议 pip-compile 锁版本)
├── tests/                  [必需] 策略级 contract tests
│   ├── test_policy_interface.py
│   ├── test_action_bounds.py
│   ├── test_inference_latency.py
│   └── test_smoke_rollout.py
└── manifest.json           [必需] 版本号 + freeze hash + 训练时间预估
```

**完整性约束**:目录中**所有文件必须同时存在**,缺一即视为合同违约,`post_policy_submit.py` 直接 fail。

---

## 2. policy.py — 编程接口

### 2.1 Policy ABC (定义在 `contracts/policy_protocol.py`)

任何对此基类的修改都需要**双方书面同意** (PR review + 双签字)。

```python
# contracts/policy_protocol.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np

class Policy(ABC):
    """所有策略必须实现此协议。AutoResearch 只通过此接口调用。"""

    @abstractmethod
    def __init__(
        self,
        config: Dict[str, Any],
        env_spec: Dict[str, Any],
    ) -> None:
        """
        Args:
            config: 从 default_config.yaml 加载,可被 search_space 中的字段覆盖。
                    实验 agent 修改 config 时,只能修改在 search_space 中声明的字段。
            env_spec: 从 task_spec.yaml 加载的观测/动作空间定义。
                     包含 observation_space, action_space, agents 等字段。
        
        约束:
            - 必须在此处完成所有重计算 (网络初始化、模型编译等)
            - act() 必须保持快速 (< 50ms)
        """

    @abstractmethod
    def reset(self, seed: int) -> None:
        """每个 episode 开始时调用。
        
        约束:
            - 必须使内部随机源 (numpy / torch) 全部受 seed 控制
            - 同一 seed 下多次 reset 后的 act 输出必须逐位一致
        """

    @abstractmethod
    def act(
        self,
        obs: Dict[str, np.ndarray],
        agent_id: str,
        info: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """
        Args:
            obs: PettingZoo Parallel 风格,key 是 agent_id (例如 "red", "blue")。
                 注意:即使你的策略只控制一方,也会收到双方的观测字典。
            agent_id: 当前需要决策的 agent。策略只输出该 agent 的动作。
            info: env 提供的诊断信息 (可选,通常用不到)。
        
        Returns:
            np.ndarray: 单个 agent 的 action,
                       形状必须严格匹配 env_spec["action_space"]["shape"]。
                       值必须在 [low, high] 范围内 (越界会被 safety_gate 拦截并扣分)。
        
        约束:
            - 必须是 pure function: 不得 print、不得修改全局状态、不得写文件
            - 单次调用延迟 < 50ms (CPU)
            - 不得读取 env 内部状态 (只能用 obs)
            - 不得抛异常 (任何错误情况返回零动作 + info 中标记)
        """

    @abstractmethod
    def load(self, checkpoint_path: str) -> None:
        """从训练产生的 checkpoint 加载权重。
        
        约束:
            - checkpoint 格式由策略 agent 自定义
            - 但 checkpoint_path 必须是单个文件路径,不是目录
            - load 后调用 act 必须 deterministic
        """

    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]:
        """返回此策略可被 search_space 覆盖的字段及类型范围。
        实验 agent 用此结果验证 search_space.yaml 是否合法。
        
        Returns:
            {
                "field_name": {
                    "type": "float" | "int" | "categorical",
                    "range": [low, high]  # for float/int
                    "choices": [...]      # for categorical
                },
                ...
            }
        """

    # ===== 可选方法 =====
    
    def supports_training(self) -> bool:
        """学习类策略返回 True,基于规则的策略返回 False。"""
        return True
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """供失败诊断使用,返回策略内部状态(注意力权重、价值估计等)。
        
        实验 agent 在 failure replay 时会调用此方法。
        如不实现则返回空字典。
        """
        return {}
```

### 2.2 实现示例(策略 agent 写)

```python
# policies/mappo_velocity_v1/policy.py
import torch
import numpy as np
from contracts.policy_protocol import Policy

class MAPPOVelocityPolicy(Policy):
    def __init__(self, config, env_spec):
        self.config = config
        self.env_spec = env_spec
        self.device = config.get("device", "cpu")
        self.network = self._build_network(
            obs_dim=env_spec["observation_space"]["shape"][0],
            act_dim=env_spec["action_space"]["shape"][0],
            hidden_size=config["hidden_size"],
        ).to(self.device)
        self.act_low = np.array(env_spec["action_space"]["low"])
        self.act_high = np.array(env_spec["action_space"]["high"])
    
    def reset(self, seed):
        torch.manual_seed(seed)
        np.random.seed(seed)
    
    def act(self, obs, agent_id, info=None):
        obs_tensor = torch.from_numpy(obs[agent_id]).float().to(self.device)
        with torch.no_grad():
            action = self.network(obs_tensor.unsqueeze(0)).squeeze(0).cpu().numpy()
        return np.clip(action, self.act_low, self.act_high)
    
    def load(self, checkpoint_path):
        state = torch.load(checkpoint_path, map_location=self.device)
        self.network.load_state_dict(state["model"])
    
    def get_config_schema(self):
        return {
            "learning_rate": {"type": "float", "range": [1e-5, 1e-3]},
            "hidden_size": {"type": "categorical", "choices": [128, 256, 512]},
            "entropy_coef": {"type": "float", "range": [0.001, 0.05]},
            "safety_penalty": {"type": "float", "range": [-100, -1]},
        }
```

---

## 3. train.py — 训练命令行接口

### 3.1 命令行签名 (字段名严格固定)

```bash
python policies/<policy_id>/train.py \
  --config <path>             \
  --scenario <path>           \
  --seed <int>                \
  --output_dir <path>         \
  --max_steps <int>           \
  --wall_time_limit <int>     \
  [--resume_from <path>]      \
  [--log_interval <int>]
```

| 参数 | 类型 | 必需 | 说明 |
|---|---|:---:|---|
| `--config` | path | ✓ | YAML 配置文件路径,实验 agent 每个 trial 生成一份 |
| `--scenario` | path | ✓ | 场景目录路径,例如 `scenarios/drone_ring_001` |
| `--seed` | int | ✓ | 训练 seed,实验 agent 用于跨 seed 验证 |
| `--output_dir` | path | ✓ | 训练产物输出目录 |
| `--max_steps` | int | ✓ | 训练步数上限 |
| `--wall_time_limit` | int (秒) | ✓ | 墙上时间上限 (硬截断) |
| `--resume_from` | path | ✗ | 从 checkpoint 恢复训练 |
| `--log_interval` | int | ✗ | 日志记录间隔,默认 1000 |

### 3.2 必需产出 (在 `output_dir` 下)

```
{output_dir}/
├── checkpoint_final.pt        [必需] 最终模型权重
├── checkpoint_best.pt         [可选] 训练过程中最优 (按 val 选)
├── training_curves.csv        [必需] 每个 log_interval 的指标
├── training_log.json          [必需] 训练摘要,见 §3.3
└── stdout.log                 [必需] 完整 stdout 输出
```

### 3.3 `training_log.json` 格式

```json
{
  "schema_version": "1.0",
  "policy_id": "mappo_velocity_v1",
  "scenario_id": "drone_ring_001",
  "config_used": { ... },
  "seed": 42,
  "started_at": "2026-05-01T10:00:00Z",
  "finished_at": "2026-05-01T11:23:45Z",
  "wall_time_seconds": 5025.3,
  "total_steps": 1000000,
  "termination_reason": "max_steps_reached",
  "final_train_metrics": {
    "mean_episode_reward": 12.3,
    "mean_episode_length": 234
  },
  "checkpoint_path": "checkpoint_final.pt",
  "checkpoint_hash": "sha256:..."
}
```

**约束**:`termination_reason` 必须是枚举之一: `max_steps_reached` | `wall_time_exhausted` | `convergence_detected` | `error`。

### 3.4 退出码

| 退出码 | 含义 | 实验 agent 行为 |
|:---:|---|---|
| `0` | 训练成功完成 | 进入评测 |
| `1` | 训练崩溃 (异常) | 标记 trial 失败,保留 stdout |
| `2` | 训练超时 (wall_time) | 仍尝试评测最后 checkpoint |
| `3` | 配置非法 (search_space 越界) | 标记为合同违约,告警 |

---

## 4. infer.py — 评测命令行接口

### 4.1 命令行签名

```bash
python policies/<policy_id>/infer.py \
  --checkpoint <path>          \
  --scenario <path>            \
  --eval_seeds <list>          \
  --output <path>              \
  [--render]                   \
  [--stress_test <name>]
```

| 参数 | 类型 | 必需 | 说明 |
|---|---|:---:|---|
| `--checkpoint` | path | ✓ | 加载的 checkpoint 路径 |
| `--scenario` | path | ✓ | 场景目录 |
| `--eval_seeds` | comma-list | ✓ | 评测 seed,例如 `100,101,102,...,119` |
| `--output` | path | ✓ | `eval_results.json` 输出路径 |
| `--render` | flag | ✗ | 是否保存渲染视频 (用于 failure replay) |
| `--stress_test` | str | ✗ | 应用 task_spec 中定义的 stress test 名称 |

### 4.2 `eval_results.json` 格式 ⚠️ 实验 Agent 直接消费此文件

```json
{
  "schema_version": "1.0",
  "policy_id": "mappo_velocity_v1",
  "checkpoint_hash": "sha256:abc123...",
  "scenario_id": "drone_ring_001",
  "stress_test": null,
  "seeds_evaluated": [100, 101, 102, ..., 119],
  "n_episodes": 200,
  "metrics": {
    "primary": {
      "name": "constrained_success_rate",
      "value": 0.87,
      "std": 0.04,
      "ci_95": [0.82, 0.92]
    },
    "secondary": {
      "avg_episode_length": { "value": 234, "std": 12 },
      "path_length": { "value": 18.5, "std": 1.2 },
      "control_smoothness": { "value": 0.78, "std": 0.05 }
    },
    "hard_constraints": {
      "collision_rate":     { "value": 0.03, "max": 0.05, "passed": true },
      "out_of_bounds_rate": { "value": 0.005, "max": 0.01, "passed": true },
      "action_violation_rate": { "value": 0.0, "max": 0.0, "passed": true }
    }
  },
  "per_seed_metrics": [
    { "seed": 100, "primary": 0.85, "collision_rate": 0.04 },
    { "seed": 101, "primary": 0.90, "collision_rate": 0.02 }
  ],
  "failure_episodes": [
    { "seed": 105, "episode_in_seed": 3, "failure_type": "collision_with_opponent",
      "trace_path": "traces/seed_105_ep_3.npz" }
  ],
  "wall_time_seconds": 142.3
}
```

**字段强约束**:
- `metrics.primary.name` 必须与 `task_spec.evaluation_metrics.primary.name` 完全一致
- `metrics.hard_constraints` 中每一项的 `name` 和 `max` 必须与 `task_spec` 一致
- `per_seed_metrics` 用于实验 agent 计算跨 seed 稳定性
- `failure_episodes` 列出失败 episode,实验 agent 用于诊断失败模式

---

## 5. default_config.yaml — 默认超参

```yaml
schema_version: "1.0"
policy_id: "mappo_velocity_v1"

# 训练超参
training:
  learning_rate: 3e-4
  batch_size: 256
  num_epochs: 4
  gamma: 0.99
  gae_lambda: 0.95
  clip_ratio: 0.2
  entropy_coef: 0.01
  value_coef: 0.5
  max_grad_norm: 0.5

# 网络结构
network:
  hidden_size: 256
  num_layers: 2
  activation: "tanh"

# 算法特定
mappo:
  shared_critic: true
  use_communication: false
  opponent_sampling_ratio: 0.3

# 安全相关
safety:
  safety_penalty: -10.0
  use_action_shield: true

# 系统
runtime:
  device: "cuda"
  num_workers: 4
```

---

## 6. search_space.yaml — 推荐搜索空间

策略 agent 给实验 agent 的"搜索建议",实验 agent 可以接受、收窄或拒绝。

```yaml
schema_version: "1.0"
policy_id: "mappo_velocity_v1"

# 推荐优先级最高的搜索维度
priority_1:
  learning_rate:
    type: "loguniform"
    low: 1.0e-5
    high: 1.0e-3
    default: 3.0e-4
  
  safety_penalty:
    type: "choice"
    values: [-1.0, -3.0, -10.0, -30.0]
    default: -10.0

# 次优先级
priority_2:
  entropy_coef:
    type: "loguniform"
    low: 1.0e-4
    high: 1.0e-1
    default: 0.01
  
  hidden_size:
    type: "choice"
    values: [128, 256, 512]
    default: 256

# 不建议搜索 (固定值更稳)
do_not_tune:
  - "training.gamma"
  - "training.gae_lambda"
  - "network.activation"

# 实验预算建议
budget_hint:
  recommended_trials: 30
  recommended_seeds_per_trial: 3
  recommended_max_steps: 1000000
```

**约束**:`search_space.yaml` 中每个字段必须出现在 `policy.get_config_schema()` 返回值中。`post_policy_submit.py` 自动校验。

---

## 7. algorithm_card.md — 算法卡片

实验 agent 写实验报告时直接引用此文件。必须包含以下章节:

```markdown
# Algorithm Card: <Policy Name>

## Family
<rule_based | MPC | PPO | MAPPO | hybrid>

## Compatible Scenarios
- 适用任务族: drone_ring_game
- 适用 formalism: POSG, Markov Game
- 不适用场景: 单智能体、连续高频控制 (>100Hz)

## Assumptions
- 假设 1
- 假设 2

## Input / Output
- Input observation: dict, shape per agent = [12]
- Output action: velocity_setpoint, shape = [4]

## Training Method
- Centralized training, decentralized execution
- Self-play with 30% historical opponents

## Safety Mechanism
- 输出经过 action_shield 裁剪到合法范围
- 检测到 NaN 自动回退到零动作

## Known Limitations
- 不擅长高速对抗 (训练时未见此分布)
- 通信丢包率 > 30% 时性能下降明显

## Expected Failure Modes
1. Ring approach hesitation (在圆环前 0.5m 处犹豫)
2. Adversarial blocking (面对激进对手时容易被截击)
3. Communication blackout cascade (通信中断后失去对手位置估计)

## Computational Requirements
- 训练: 1× A100, ~2 小时, 1M steps
- 推理: CPU 即可, < 10ms per act
```

---

## 8. tests/ — 必需的 contract tests

策略 agent 必须自带这些测试,实验 agent 在使用前**强制运行**:

| 测试 | 检查项 | 失败处理 |
|---|---|---|
| `test_policy_interface.py` | 实现了 Policy ABC 全部方法 | 直接拒收 |
| `test_action_bounds.py` | 1000 个随机 obs 下 action 全部在合法范围 | 直接拒收 |
| `test_inference_latency.py` | 单次 act < 50ms (CPU) | 警告但不拒收 |
| `test_smoke_rollout.py` | 能跑完一个完整 episode 不崩溃 | 直接拒收 |
| `test_seed_determinism.py` | 同 seed 两次 reset+act 结果一致 | 直接拒收 |

---

## 9. manifest.json — 冻结凭证

```json
{
  "schema_version": "1.0",
  "policy_id": "mappo_velocity_v1",
  "version": "1.0.0",
  "created_at": "2026-05-02T14:00:00Z",
  "frozen_at": "2026-05-02T14:30:12Z",
  "freeze_hash": "sha256:6b9e...",
  "compatible_scenarios": ["drone_ring_001", "drone_ring_002"],
  "compatible_scenario_versions": [">=1.0.0", "<2.0.0"],
  "files": {
    "policy.py":         "sha256:...",
    "train.py":          "sha256:...",
    "infer.py":          "sha256:...",
    "default_config.yaml": "sha256:...",
    "search_space.yaml": "sha256:..."
  },
  "validation": {
    "interface_check": "passed",
    "contract_tests": { "passed": 5, "failed": 0 },
    "smoke_test": "passed"
  },
  "training_estimate": {
    "wall_time_seconds": 5400,
    "min_gpu_memory_gb": 8,
    "expected_primary_metric": 0.65
  }
}
```

**冻结规则**:
- 一旦 `frozen_at` 写入,`policy.py`、`train.py`、`infer.py` 变为只读
- 实验 agent 只能修改 config (在 search_space 范围内)
- 修改源码 = 必须开新 `policy_id` 或新版本号

---

## 10. 实验 Agent 的使用流程

```python
# AutoResearch 内循环中的伪代码
def run_trial(trial_id, hypothesis, config_override):
    # 1. 加载冻结的策略包
    package = load_policy_package("policies/mappo_velocity_v1")
    assert package.manifest["frozen_at"] is not None
    
    # 2. 构造 trial config
    trial_config = merge(package.default_config, config_override)
    validate_against_schema(trial_config, package.search_space)
    
    # 3. 写 trial 配置文件
    config_path = f"experiments/exp_001/trials/{trial_id}/config.yaml"
    save_yaml(trial_config, config_path)
    
    # 4. 调用 train.py
    output_dir = f"experiments/exp_001/trials/{trial_id}"
    subprocess.run([
        "python", f"policies/mappo_velocity_v1/train.py",
        "--config", config_path,
        "--scenario", "scenarios/drone_ring_001",
        "--seed", str(trial_seed),
        "--output_dir", output_dir,
        "--max_steps", "1000000",
        "--wall_time_limit", "3600",
    ], check=True)
    
    # 5. 调用 infer.py 评测
    eval_results_path = f"{output_dir}/eval_results.json"
    subprocess.run([
        "python", f"policies/mappo_velocity_v1/infer.py",
        "--checkpoint", f"{output_dir}/checkpoint_final.pt",
        "--scenario", "scenarios/drone_ring_001",
        "--eval_seeds", ",".join(map(str, val_seeds)),
        "--output", eval_results_path,
    ], check=True)
    
    # 6. 解析结果,送入 promotion gate
    results = load_json(eval_results_path)
    return promotion_gate.evaluate(results, hypothesis)
```

---

## 11. 联调检查清单 (M1 节点用)

朋友交付策略包时,实验 agent 这边需要验证:

- [ ] `policies/<policy_id>/` 目录完整,§1 列出的文件全部存在
- [ ] 能 `python -c "from contracts.policy_protocol import Policy; from policies.<id>.policy import *"` 导入
- [ ] `python -m pytest policies/<policy_id>/tests/` 全绿
- [ ] 能用 mock config 调用 `train.py` 跑 100 步不崩溃
- [ ] 能用 random checkpoint 调用 `infer.py` 产出符合 §4.2 schema 的 `eval_results.json`
- [ ] `manifest.json` 中的 `freeze_hash` 已写入,且与文件实际 hash 一致
- [ ] `search_space.yaml` 中的字段全部出现在 `policy.get_config_schema()` 返回值中
- [ ] `algorithm_card.md` 包含 §7 列出的所有章节

任意一项不通过 → 当场退回,不进入实验阶段。

---

## 12. 反馈通道 (实验 → 策略)

当实验 agent 触发回退时(连续 N 轮 trial 收敛但仍未达 SLA),会向策略 agent 提交标准化报告。

详见 `INTERFACE_3_AUTORESEARCH_FEEDBACK.md` (待补充,目前先约定文件位置):

```
experiments/<exp_id>/regression_report.md
```

策略 agent 收到此报告后,可以:
1. 升级算法 (开新 `policy_id`)
2. 标注为"已知问题"并继续
3. 向场景 agent 回退 (写 `spec_inconsistency.md`)

**严禁实验 agent 直接修改 `policies/<policy_id>/` 下任何文件。**
