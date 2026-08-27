# Algorithm Card: drone_ring_lossy_3ring_rule_v1

## Family

Deterministic rule-based navigation / interception policy.

## Compatible Scenarios

- `drone_ring_game`
- 1v1 轻量 2D 场景
- 丢包或完美通信的多环追击变体

## Assumptions

- 观测维度为 12，且目标环方向与对手相对状态可能被置零表示丢包。
- 红方需要优先保证穿环成功率，蓝方需要抑制红方但不能通过高碰撞率作弊。
- 环境为双积分近似而非真实飞控。

## Input / Output

- 输入：单 agent 12 维观测、`agent_id`、可选 `info`
- 输出：4 维连续动作，只有前两维作为平面加速度控制，最终统一 `np.clip`

## Training Method

`train.py` 为 no-op 训练入口，只负责记录配置并产出可复现 checkpoint 载荷，供实验阶段统一调用。

## Safety Mechanism

- 严格动作裁剪
- 红方近距避碰与切向绕行
- 蓝方近距退让，避免靠碰撞刷拦截
- 丢包时使用短期记忆平滑回退，减少零观测抖动

## Known Limitations

- 策略不学习，仅依赖手工规则
- 记忆只覆盖局部短时观测，无法处理长时间连续失联后的全局规划
- 仍是 M1 轻量环境，指标仅说明流程闭环，不代表真实机载效果

## Expected Failure Modes

- 连续多帧目标方向丢失时，红方会沿最近一次有效方向继续推进，可能在后续环附近偏航
- 蓝方截击参数过高时会造成碰撞约束不满足
- 安全距离过大时红方绕行动作过强，导致 episode 变长

## Computational Requirements

- CPU 即可
- 单次推理为微秒到毫秒级
- sweep 主要成本来自 rollout，而非训练
