# Scenario Model: drone_ring_lossy_3ring_001

## Formalism

`POSG`

## State

- 红方 `red_0` 和蓝方 `blue_0` 都是 2D 点质量双积分近似。
- 红方目标是依次穿过 3 个圆环；蓝方目标是在边界内追击并制造碰撞式拦截。
- Episode 在红方完成全部圆环、蓝方碰撞成功、任一方出界或达到 `max_steps=200` 时结束。

## Observation

每个 agent 使用 12 维观测：

1. 自身位置 `x, y`
2. 自身速度 `vx, vy`
3. 对手相对位置 `dx, dy`
4. 对手相对速度 `dvx, dvy`
5. 剩余环比例
6. 当前目标环方向 `ux, uy`
7. 当前目标环距离

在 `lossy` 通信模式下，对手相对状态切片 `obs[4:8]` 与目标环切片 `obs[9:12]` 会以 `10%` 概率独立清零，表示本步无法可靠接收对应信息。

## Action

- 连续动作 4 维：`[ax, ay, aux_0, aux_1]`
- 当前环境只消费前两维作为平面加速度；后两维保留接口兼容位
- 所有动作都会被裁剪到 `[-2, 2] x [-2, 2] x [-1, 1] x [-1, 1]`

## Evaluation

- Primary metric：`success_rate`
- Secondary：`collision_rate`、`timeout_rate`、`episode_length`
- Hard constraints：`collision_rate <= 0.05`、`out_of_bounds_rate <= 0.01`、`action_violation_rate <= 0.0`

## Notes

- 场景环境在相同 `seed` 下完全确定，包含丢包事件序列。
- 该实现是 M1 轻量可验证环境，不追求真实无人机气动精度。
