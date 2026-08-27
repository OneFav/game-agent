# Assumptions

- `dt -> 0.18`：采用较稳定的 2D 双积分离散步长，让 200 步内完成三环成为可实现但非平凡的任务。
- `ring_radius -> 0.55`：比基线略大，减少单步丢包导致的精确穿环失败，但仍要求红方持续贴近门心。
- `collision_radius -> 0.28`：延续轻量追击/拦截判定，不把近距离擦肩误判为碰撞。
- `boundary -> 9.0`：收紧边界，避免蓝方无限外扩追击。
- `drop semantics -> observation slice masking`：将 10% 丢包实现为对手相对状态与目标环方向/距离的独立随机清零；同一 seed 下完全确定。
- `shared packet-loss model -> both agents`：红蓝双方都受同一通信噪声机制影响，避免只对单方引入不对称便利。
- `ring layout -> alternating y offsets`：三环沿 x 轴递进，并在 y 轴上交替偏移，用最小复杂度体现“多环”而不是三个位于同一直线的简化情形。
