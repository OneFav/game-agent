# AutoResearch Report: wide_slalom_2v2_exp_001

## Summary

- Trials executed: 9
- Seeds per trial: 3 (100, 101, 102)
- Best trial: `trial_0008`
- Primary metric: `team_score = 6.000`
- Secondary: `avg_red_score = 6.000`, `avg_blue_score = 7.000`, `avg_episode_length = 600.000`
- Hard constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- Decision: promote

## Coupling Load Empty-Field Test

- Utility definition: `U_R = red_score - blue_score`
- Empty condition: blue agents are spawned far from the gate field and forced to zero actions; red policy, best config, scenario wrapper, and seeds are unchanged.
- Seeds: `100, 101, 102`
- `U_R(red, empty) = 6.000`
- `U_R(red, true_blue) = -1.000`
- `Delta(coupling load) = 7.000`
- Decision: pass (`Delta > 0`), so the true blue side imposes a measurable coupled load on red utility.
- Artifact: `coupling_load_test.json`

## Best Config

```yaml
desired_speed: 5.0
position_gain: 1.2
velocity_gain: 2.2
risk_margin: 0.9
boundary_margin: 1.2
turn_steps: 12
turn_lookahead: 5.0
risk_lookahead_steps: 18
brake_release_speed: 0.35
lane_spacing: 1.2
gate_approach_offset: 4.0
gate_exit_offset: 3.0
separation_gain: 4.0
reserved_action_value: 0.0
```

## Trial Notes

- `trial_0008`: feasible=true, team_score=6.000, collision_rate=0.000, avg_episode_length=600.000, decision=promote
- `trial_0009`: feasible=true, team_score=6.000, collision_rate=0.000, avg_episode_length=600.000, decision=continue
- `trial_0004`: feasible=true, team_score=3.000, collision_rate=0.000, avg_episode_length=600.000, decision=continue
- `trial_0006`: feasible=true, team_score=3.000, collision_rate=0.000, avg_episode_length=600.000, decision=continue
- `trial_0007`: feasible=true, team_score=3.000, collision_rate=0.000, avg_episode_length=600.000, decision=continue
- `trial_0001`: feasible=false, team_score=3.000, collision_rate=1.000, avg_episode_length=276.000, decision=rollback
- `trial_0002`: feasible=false, team_score=3.000, collision_rate=1.000, avg_episode_length=276.000, decision=rollback
- `trial_0003`: feasible=false, team_score=3.000, collision_rate=1.000, avg_episode_length=276.000, decision=rollback
- `trial_0005`: feasible=false, team_score=3.000, collision_rate=1.000, avg_episode_length=572.000, decision=rollback

## Notes

- Ranking uses only `task_spec.evaluation_metrics`: feasible first, then `team_score` descending, then `avg_episode_length` ascending.
- The promoted configuration came from the real 3D `swarm_combat` wrapper rather than the legacy 2D compatibility shell.
- `_smoke/` retains the earlier single-config validation artifact for the recorded pilot iteration.
