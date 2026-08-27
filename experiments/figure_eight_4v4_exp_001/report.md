# AutoResearch Report: figure_eight_4v4_exp_001

## Summary

- Trials executed: 12
- Seeds per trial: 3 (100, 101, 102)
- Best trial: `trial_0001`
- Primary metric: `team_score = 4.000`
- Hard constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- Decision: promote

## Best Config

```yaml
desired_speed: 5.4
position_gain: 1.3
velocity_gain: 2.2
risk_margin: 0.9
boundary_margin: 1.2
turn_steps: 12
turn_lookahead: 6.0
risk_lookahead_steps: 18
brake_release_speed: 0.35
lane_spacing: 1.4
gate_approach_offset: 4.5
gate_exit_offset: 3.5
separation_gain: 4.5
defender_mode: escort
```

## Top 3

1. `trial_0001` -> team_score=4.000, collision_rate=0.000, avg_episode_length=1200.0, decision=promote
2. `trial_0002` -> team_score=4.000, collision_rate=0.000, avg_episode_length=1200.0, decision=promote
3. `trial_0003` -> team_score=4.000, collision_rate=0.000, avg_episode_length=1200.0, decision=promote

## Notes

Ranking uses `task_spec.evaluation_metrics` only. `reward_structure` was not used for promotion or sorting.
The sweep is the full cartesian product of the declared parameter values: desired_speed x lane_spacing x turn_lookahead x risk_margin x defender_mode.
