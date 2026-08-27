# vertical_wave_3v3_001 场景模型说明

## 任务摘要

该场景是一个 3D 六机对抗任务：红蓝双方各 3 机，其中 2 架赛车机负责穿越 `vertical_wave` 门序列并累积团队得分，1 架防守机负责护航己方赛车机并压制对方路线。环境真实执行引擎使用 `swarm_combat`，但为了兼容当前仓库合同层，场景包以 `task_family: drone_ring_game` 冻结。

## 状态与动作

- **单机状态观测**：94 维固定长度向量。
  - 自身位置/速度：6 维
  - 其他 5 机的相对位置/速度/队伍角色标记：40 维
  - 6 个门的相对中心、法向量、冷却信息：48 维
- **动作**：3 维连续加速度设定 `[ax, ay, az]`。

## 得分机制

- `gate_pass_reward = 1.0`
- 真实环境内部用 `team_scores[RED/BLUE]` 累积有效过门得分。
- 本场景定义的 `team_score` 指标即红方团队有效过门数，因此 README 的 `team_score >= 3.0` 可直接解释为红方平均至少完成 3 次有效过门。

## 终止规则

- 任何碰撞或出界触发终止。
- 任何一方达到目标过门数可终止。
- 600 步到达则截断。

## 合同兼容说明

当前共享 `scenario_schema.yaml` 只允许 `task_family: drone_ring_game`。因此此场景包通过 `scenario_parameters.engine: swarm_combat` 和 `env_config.yaml` 显式声明真实执行引擎。下游策略和实验阶段必须尊重这一适配边界，不能误把该场景当作 2D 1v1 环穿越任务。
