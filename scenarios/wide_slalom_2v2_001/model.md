# wide_slalom_2v2_001 Model

## Formalism

- `task_family`: `swarm_combat`
- `formalism`: `POSG`
- Teams act simultaneously in a shared 3D gate-racing arena.

## Roles

- `red_racer_0`: race through the `wide_slalom` gates and maximize red-team score.
- `red_defender_0`: escort the red racer and preserve safe spacing.
- `blue_racer_0`: contest the same gate sequence from the opposing side.
- `blue_defender_0`: intercept the red racer while avoiding hard collisions.

## Dynamics And Scoring

- Shared engine: `game_agent.envs.swarm_combat.SwarmCombatEnv`
- Racer dynamics: `double_integrator`
- Defender dynamics: `damped_double_integrator`
- A valid gate pass contributes `1.0` to the passing team score.
- Episodes terminate on hard collision / safety violation, out of bounds, or timeout at 600 steps.

## Evaluation

- Primary metric: `team_score` = average cumulative red-team score across validation seeds.
- Secondary metrics: `avg_red_score`, `avg_blue_score`, `avg_episode_length`, `red_win_rate`, `draw_rate`.
- Hard constraints: `collision_rate <= 0.05`, `out_of_bounds_rate <= 0.01`, `action_violation_rate == 0.0`.
