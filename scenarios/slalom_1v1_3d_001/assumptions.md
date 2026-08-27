# Assumptions

| 参数 | 默认值 | 理由 |
| --- | --- | --- |
| `task_family` | `drone_ring_game` | 共享 `scenario_schema` 仍未开放 `swarm_combat` 枚举，本次通过场景包内部适配层承载真实 3D 语义。 |
| `formalism` | `MarkovGame` | 示例 4 只描述 1v1 完美通信对抗，没有局部观测要求。 |
| `gate_count` | `5` | 直接采用 `build_gate_layout("slalom")` 的现有门序列。 |
| `gate_pass_reward` | `1.0` | 让 README 的 `team_score >= 1.0` 与环境累计门分同量纲。 |
| `spawn_red` | `(-22.0, -1.5, 4.0)` | 与 `slalom` 门群左侧对齐，给红方足够的进门准备距离。 |
| `spawn_blue` | `(22.0, 1.5, 4.0)` | 与红方镜像对称，保持公平。 |
| `target_score` | `1.0` | README 示例 4 的达标线就是 `team_score >= 1.0`，因此本场景在任一方达到阈值后立即结束，避免达标后的无效门框碰撞污染评估。 |
| `team_score_definition` | `red sequential gate score` | README 未明确分数口径，本次显式固定为红方顺序过门累计得分。 |
