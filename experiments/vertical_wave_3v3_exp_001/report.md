# AutoResearch Report: vertical_wave_3v3_exp_001

## Summary

- Trials executed: 12
- Seeds per trial: 3 (11, 17, 23)
- Best trial: `trial_0006`
- Primary metric: `team_score = 6.000`
- Hard constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- Decision: promote

## Best Config

```yaml
desired_speed: 5.5
position_gain: 1.3
velocity_gain: 2.2
risk_margin: 1.2
boundary_margin: 1.2
turn_steps: 12
turn_lookahead: 6.0
risk_lookahead_steps: 18
brake_release_speed: 0.35
lane_spacing: 1.2
gate_approach_offset: 4.5
gate_exit_offset: 3.5
separation_gain: 4.5
defender_mode: escort
```

## Notes

- Ranking uses `evaluation_metrics` only: feasible first, then `team_score`, then `score_margin`, then `avg_episode_length`.
- This experiment package is a local swarm_combat adaptation because the shared `src/game_agent/autoresearch/runner.py` is currently 1v1-specific.
- The `_smoke/` baseline directory is preserved as a documented pre-sweep probe rather than a temporary artifact.