# slalom_1v1_3d_rule_v1 Algorithm Card

## Family

规则策略，面向 `swarm_combat` 语义的 3D 双积分器 1v1 竞逐/拦截任务。

## Compatible Scenarios

- `slalom_1v1_3d_001`
- 其他拥有 64 维冻结观测、3 维加速度动作、顺序门评分逻辑的 1v1 3D 对抗场景

## Assumptions

- 双方都能读取冻结观测中的下一目标门相对向量
- 场景按顺序门定义 `team_score`
- 完美通信，无延迟和丢包
- 规则策略不训练，只靠配置扫参

## Input/Output

- 输入：`obs` 为单智能体 64 维观测，或 hook smoke test 的 12 维简化观测
- 输出：单智能体 3 维加速度动作；若环境给出 4 维边界，则保留兼容形状但只主动控制前 3 维

## Training Method

`train.py` 为 no-op checkpoint 准备脚本，仅负责把配置和元数据写入 trial 目录。

## Safety Mechanism

1. 动作统一 `np.clip`
2. 近距离对手避碰
3. 边界回推
4. 速度阻尼
5. 任何异常回退零动作

## Known Limitations

- 不显式建模门框碰撞几何
- 蓝方为拦截型启发式，不保证全局最优
- 不利用历史轨迹，只看单步冻结观测

## Expected Failure Modes

- 红蓝近距离对穿时仍可能触发双负
- 高速进门时如果 `prediction_horizon` 过小，蓝方会跟丢红方
- 若场景换成多机协同，本策略没有队友分工逻辑

## Computational Requirements

- CPU 上每步推理仅向量运算
- 无训练显存需求
