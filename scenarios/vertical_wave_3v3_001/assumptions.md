# vertical_wave_3v3_001 默认假设

- `communication.mode -> perfect`
  - 用户未指定延迟或丢包；为减少额外变量，默认完美通信。
- `gate_pass_reward -> 1.0`
  - README 目标写的是 `team_score >= 3.0`。将有效过门奖励归一到 1.0 后，`team_score` 可以直接解释为团队有效过门数，避免把奖励尺度混入指标解释。
- `spawn_mode -> random`
  - 这是用户明确要求，直接映射到 `swarm_combat` 的随机出生模式。
- `max_steps -> 600`
  - 这是当前用户请求中的超时步数；旧的 800 步示例产物不得作为本轮完成依据。
- `spawn_min_separation -> 1.8`
  - 3v3 随机出生比 2v2 更容易出现初始拥挤，适度提高最小间距以降低起飞即碰撞风险。
- `collision_ends_episode -> true`
  - 当前目标强调前视碰撞检测和安全约束，保守地把碰撞视为 episode 失败终止。
- `out_of_bounds_ends_episode -> true`
  - 与现有参考环境一致，避免通过出界换取路线捷径。
- `task_family -> drone_ring_game`
  - 这是合同兼容妥协，不代表真实引擎语义。真实引擎在 `scenario_parameters.engine` 与 `env_config.yaml` 中声明为 `swarm_combat`。
