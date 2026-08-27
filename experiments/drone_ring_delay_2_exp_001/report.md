# AutoResearch Report: drone_ring_delay_2_exp_001

## Summary
- Best trial: `trial_0013`
- success_rate: 1.000
- collision_rate: 0.000
- avg_episode_length: 26.000

## Iteration Notes
- Baseline family: deterministic rule policy with delayed blue pursuit.
- Fixed delay parameter: `delay_steps = 2`.
- Sweep focus: `speed_scale`, `intercept_gain`, `safety_margin`.
- Promotion threshold: `success_rate >= 0.55`; observed best = 1.000.

## Top 3 Trials
- `trial_0013`: success_rate=1.000, collision_rate=0.000, avg_episode_length=26.000, decision=promote
- `trial_0014`: success_rate=1.000, collision_rate=0.000, avg_episode_length=26.000, decision=promote
- `trial_0015`: success_rate=1.000, collision_rate=0.000, avg_episode_length=26.000, decision=promote

## Trial Hypotheses
- `trial_0013`: speed_scale=1.2, intercept_gain=0.8, safety_margin=0.1 should trade off ring traversal speed against delayed blue pursuit stability.
- `trial_0014`: speed_scale=1.2, intercept_gain=0.8, safety_margin=0.2 should trade off ring traversal speed against delayed blue pursuit stability.
- `trial_0015`: speed_scale=1.2, intercept_gain=1.0, safety_margin=0.1 should trade off ring traversal speed against delayed blue pursuit stability.
- `trial_0016`: speed_scale=1.2, intercept_gain=1.0, safety_margin=0.2 should trade off ring traversal speed against delayed blue pursuit stability.
- `trial_0017`: speed_scale=1.2, intercept_gain=1.2, safety_margin=0.1 should trade off ring traversal speed against delayed blue pursuit stability.
