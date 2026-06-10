# AutoResearch Report: wide_slalom_2v2_exp_001

## Summary

- Trials executed: 9
- Seeds per trial: 3 (100, 101, 102)
- Best trial: `trial_0007`
- Primary metric: `success_rate = 1.000`
- Hard constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- Decision: promote

## Best Config

```yaml
racer_gain: 1.0
escort_gain: 0.72
intercept_gain: 0.75
block_gain: 0.62
avoidance_radius: 2.5
avoidance_gain: 0.45
velocity_damping: 0.1
prediction_horizon: 0.35
reserved_action_value: 0.0
```

## Notes

Ranking uses `task_spec.evaluation_metrics` only. `reward_structure` was not used for promotion or sorting.
The sweep uses the priority_1 deterministic grid for `racer_gain` and `intercept_gain` against the 32-dimensional observation scenario.
