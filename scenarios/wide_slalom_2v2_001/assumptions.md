# Assumptions

- `communication.mode -> perfect`: 原始 prompt 未给通信延迟或丢包，因此采用 README 示例的默认完美通信。
- `task_family -> swarm_combat`: 示例 5 明确属于 3D 多机编队对抗，不再沿用旧版 `drone_ring_game` 兼容壳。
- `team_score -> red cumulative gate score`: 当前实验按红方累计得分做主指标，蓝方累计得分和胜率作为 secondary 指标保留。
- `gate_pass_reward -> 1.0`: 为了让 `team_score >= 2.0` 与 README 示例阈值保持同量纲，单次有效穿门计 1 分。
- `target_score -> null`: 不提前截断于 2 分，保持完整 600 步 rollout 以观察护航/拦截在全程 wide_slalom 中的稳定性。
- `spawn layout -> fixed mirrored starts`: 未指定随机出生，因此使用对称固定出生点，便于可复现地比较 trial 间差异。
- `policy interface -> normalized 4D action`: 共享 `swarm_combat` 环境原生使用 3D 加速度，本场景 wrapper 保留第 4 维保留位以兼容本地 Policy hook。
