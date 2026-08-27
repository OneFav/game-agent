# AutoResearch Report: drone_ring_delay_2_ppo_exp_002_dense_curve

## Outcome

- Best trial: `trial_0003`
- Primary metric: `success_rate` (maximize)
- Baseline: `policy.untrained_initialization`
- Direction-aware improvement over baseline: +1

## Raw comparison table

| Metric | Direction | Baseline mean ± std | Best mean ± std | Raw delta |
|---|---:|---:|---:|---:|
| success_rate | maximize | 0 ± 0 | 1 ± 0 | +1 |
| collision_rate | minimize | 0 ± 0 | 0 ± 0 | +0 |
| avg_episode_length | minimize | 66 ± 0 | 28 ± 0 | -38 |
| out_of_bounds_rate | minimize | 1 ± 0 | 0 ± 0 | -1 |
| action_violation_rate | minimize | 0 ± 0 | 0 ± 0 | +0 |

## Standard visualizations

- [Training design](figures/training_design.png)
- [Training process](figures/training_process.png)
- [Training effect](figures/training_effect.png)
- [Visualization manifest](figures/visualization_manifest.json)

Training reward is explanatory only. Promotion remains governed by `scenario.evaluation_metrics` and hard constraints.
