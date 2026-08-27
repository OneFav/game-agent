# AutoResearch Report: drone_ring_basic_1v1_exp_002_visualized

## Outcome

- Best trial: `trial_0013`
- Primary metric: `success_rate` (maximize)
- Direction-aware improvement over default baseline: +0

## Raw comparison table

| Metric | Direction | Default mean ± std | Best mean ± std | Raw delta |
|---|---:|---:|---:|---:|
| success_rate | maximize | 1 ± 0 | 1 ± 0 | +0 |
| collision_rate | minimize | 0 ± 0 | 0 ± 0 | +0 |
| avg_episode_length | minimize | 29 ± 0 | 26 ± 0 | -3 |
| out_of_bounds_rate | minimize | 0 ± 0 | 0 ± 0 | +0 |
| action_violation_rate | minimize | 0 ± 0 | 0 ± 0 | +0 |

## Standard visualizations

- [Training design](figures/training_design.png)
- [Training process](figures/training_process.png)
- [Training effect](figures/training_effect.png)
- [Visualization manifest](figures/visualization_manifest.json)

Training reward is explanatory only. Promotion remains governed by `scenario.evaluation_metrics` and hard constraints.
