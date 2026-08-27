# figure_eight_4v4_001 Model

## Formalism

This scenario is a partially observable stochastic game (POSG). Eight agents act simultaneously: two red racers, two red defenders, two blue racers, and two blue defenders.

## Roles

Red racers are the task-progress agents and aim to accumulate figure-eight gate score. Red defenders serve as safety-preserving escorts. Blue racers contest the same bidirectional gate layout from the opposite traversal direction. Blue defenders provide traffic pressure near the crossover region but remain wrapped by the same safety interface as every other agent.

## State, Observations, and Actions

The frozen contract uses a per-agent observation vector of shape `(110,)` and a per-agent action vector of shape `(3,)`. The observation concatenates self state, seven other-drone relative state blocks, and six gate-relative geometry/cooldown blocks. The action is a clipped 3D acceleration command consumed by the wrapper and forwarded into `SwarmCombatEnv`.

## Transition and Communication

The executable core is `game_agent.envs.swarm_combat.SwarmCombatEnv` configured for `figure_eight`, `4v4`, bidirectional team-forward gate passing, and `DampedDoubleIntegrator3D` dynamics for both racers and defenders. Communication remains `perfect`, so no delayed or dropped packets are introduced.

## Rewards and Metrics

Reward components are shaping signals only. The primary evaluation metric is `team_score`, defined as the average red team effective gate-pass count with `gate_pass_reward = 1.0`. This keeps the README target `team_score >= 4.0` on the same scale as the environment score and keeps the metric name disjoint from reward component names.

## Termination

The episode ends on collision, out-of-bounds, or timeout at `max_steps = 1200`. The wrapper exposes collision/out-of-bounds/action clipping flags through per-agent info so downstream policy tests and experiment ranking can treat hard constraints separately from reward shaping.

## Compatibility Note

The shared `scenario_schema.yaml` and stock AutoResearch runner still encode the older `drone_ring_game` contract. This package therefore keeps `task_family: drone_ring_game` for hook compatibility while freezing the real `swarm_combat` semantics in `env.py` and `env_config.yaml`.
