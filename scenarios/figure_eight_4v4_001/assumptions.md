# Assumptions

| Parameter | Value | Reason |
| --- | --- | --- |
| `task_family` | `drone_ring_game` | Shared scenario schema and hooks are still locked to the older contract; the real 4v4 3D semantics are preserved in `scenario_parameters` plus the wrapper environment. |
| `semantic_task_family` | `swarm_combat` | The README example is a 3D multi-drone confrontation rather than the original 2D ring runner task. |
| `formalism` | `POSG` | The prompt explicitly contains red/blue adversarial teams, role asymmetry, and simultaneous decision-making. |
| `gate_layout` | `figure_eight` | Explicitly requested by the example text and supported by `build_gate_layout("figure_eight")`. |
| `gate_count` | `6` | Derived from the existing swarm combat layout implementation for `figure_eight`. |
| `max_steps` | `1200` | Explicitly requested by the example text. |
| `communication.mode` | `perfect` | The prompt does not request delay or packet loss, and the README example does not add communication noise. |
| `spawn_mode` | `fixed` | Fixed starts make the wrapper deterministic across seeds and avoid conflating policy sweep with spawn randomness. |
| `spawn_red_positions` | `[(-22,-6,4), (-22,-2,5), (-24,-8,4.5), (-24,0,5.5)]` | Staggered red launch lanes reduce immediate intra-team conflicts while preserving a compact figure-eight formation. |
| `spawn_blue_positions` | `[(22,6,4), (22,2,5), (24,8,4.5), (24,0,5.5)]` | Mirrored blue launches preserve the requested 4v4 symmetry and leave the crossing zone uncontested at reset. |
| `dynamics` | `DampedDoubleIntegrator3D` for racers and defenders | The prompt explicitly requires damped double integrator dynamics rather than the mixed default racer/defender dynamics. |
| `gate_pass_reward` | `1.0` | Makes `team_score` numerically equal to effective red gate-pass count so the README threshold remains interpretable. |
| `target_score` | `null` | The rollout is allowed to continue until timeout so the measured `team_score` reflects sustained figure-eight progress instead of early-stop reward shaping. |
| `observation_space.shape` | `[110]` | Native `SwarmCombatEnv` observation length for 8 drones and 6 gates is `6 + 7*8 + 6*8 = 110`. |
| `action_space.shape` | `[3]` | The native environment consumes 3D acceleration commands; keeping the wrapper action identical avoids a lossy adapter. |
| `hard_constraints` | `collision_rate <= 0.05`, `out_of_bounds_rate <= 0.01`, `action_violation_rate <= 0.0` | Conservative feasibility gates reflect the user’s request for a stable policy plus 3D visualization output. |
