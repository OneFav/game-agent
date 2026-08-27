# slalom_1v1_3d_001 Model

## Formalism

`MarkovGame`

## Summary

该场景把 README 示例 4 的“3D 回转门双人对抗”冻结为一个 1v1、完美通信、双积分器动力学的 3D 对抗任务。红方与蓝方各控制 1 架赛车机，围绕 `slalom` 门序列争夺顺序过门得分；碰撞和出界都会直接终止回合。

## State And Action

- 状态执行内核来自 `game_agent.envs.swarm_combat.SwarmCombatEnv`
- 场景合约观测为 64 维定长向量，包含：
  - 自身 3D 位置、3D 速度
  - 对手相对位置、相对速度
  - 下一目标门的相对几何
  - 团队得分、已过门数、边界裕度、步数进度
  - 全部 5 个门的相对中心、冷却比率与前向距离
- 动作为 3 维连续加速度命令 `[ax, ay, az]`

## Score Definition

- `team_score` 采用**红方顺序过门累计得分**
- 每次合法顺序过门记 `1.0`
- 蓝方得分用于对抗分析与 tie-break，不作为主目标

## Termination

- 任一方达到 `team_score = 1.0`
- 任一碰撞
- 任一出界
- 达到 400 步超时
