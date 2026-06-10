# Assumptions

| Parameter | Value | Reason |
| --- | --- | --- |
| task_family | `drone_ring_game` | The current scenario schema only allows `drone_ring_game`; the richer 2v2 semantics are recorded as scenario parameters instead of changing shared contracts. |
| formalism | `POSG` | The request explicitly requires POSG and the task contains adversarial red/blue interception with partial role-specific observations. |
| gate_count | `6` | The plan points to the existing `wide_slalom` layout with six gates. |
| gate coordinates | `[(-15,-6), (-9,5), (-3,-5), (3,5), (9,-5), (15,6)]` | The plan references `build_gate_layout("wide_slalom")`; these are the corresponding 2D projections for the M1-compatible environment. |
| max_steps | `600` | The request explicitly specifies 600 steps. |
| communication.mode | `perfect` | The request explicitly specifies perfect communication; no delay or packet loss is modeled. |
| observation_space.shape | `[32]` | The plan requires fixed observations that include teammate, both opponents, gate state, and role features; the policy remains backward-compatible with 12-dimensional smoke-test observations. |
| action_space.shape | `[4]` | Current M1 policy interface expects 4-dimensional per-agent actions. Only the first two entries are applied as 2D velocity commands. |
| action_space.low/high | `[-1,-1,-1,-1]` / `[1,1,1,1]` | Conservative normalized action bounds keep policy outputs stable and satisfy the action shape/low/high contract. |
| dynamics | deterministic 2D velocity integration | The reference 1v1 `drone_ring_game` is 2D and the hook prioritizes importability/determinism over full 3D swarm dynamics. |
| initial_positions | fixed role-specific positions | Fixed starts make `reset(seed)` exactly reproducible and preserve clear red/blue role separation. |
| boundary | `25.0` | Matches the wide slalom gate span and keeps all six gates inside the playable field. |
| collision_radius | `0.5` | Conservative safety radius aligned with the swarm combat drone default. |
| interception_radius | `0.8` | Conservative threshold based on inter-team safe distance from the swarm combat defaults. |
| primary metric | `success_rate` | Downstream M1 runners already consume success-style metrics; it does not duplicate any reward component name. |
| train/validation seeds | train `0..9`, val `[100,101,102]` | Small deterministic seed sets are sufficient for M1 handoff and avoid over-specifying the later experiment plan. |
