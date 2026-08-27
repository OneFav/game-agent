# AutoResearch Round 3: red

## Scope
- Scenario: `scenarios/vertical_wave_3v3_001/`
- Policy: `policies/vertical_wave_3v3_rule_v1_r03_red/`
- Target side: `red`; frozen opponent: `blue`
- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.
- Sweep: 29 trials rerun after red-only code iteration 1.
- Ranking: feasible hard constraints first, then `team_score`/red utility descending, then `avg_episode_length` ascending.

## Best Trial
- Best trial: `trial_0021`
- red_utility: 8.667
- blue_utility: 8.000
- red_utility - blue_utility: 0.667
- hard_constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- primary std across seeds: 2.494
- best_response_gain_red: 3.667
- coupling load: U_R(red,empty_blue)=11.667, U_R(red,true_blue)=8.667, delta_R=3.000
- decision: PASS

## Hypotheses And Results
The initial parameter sweep failed because rank-1 was safe but red-negative, while higher-red candidates hit inter-team safety collisions. Code iteration 1 added a red-only inter-team buffer; BluePolicy and frozen blue parameters were not changed.
The winning hypothesis was: Full priority_1 continuation: red_desired_speed=6.4, red_risk_margin=0.8, red_lane_spacing=1.6 should search the remaining declared red parameter grid against frozen Round-2 blue.

## Leaderboard Top 3
1. `trial_0021`: feasible=True, red-blue=0.667, red_score=8.667, collision=0.000, delta_R=3.000000
2. `trial_0015`: feasible=True, red-blue=1.000, red_score=8.333, collision=0.000, delta_R=n/a
3. `trial_0018`: feasible=True, red-blue=0.667, red_score=6.667, collision=0.000, delta_R=n/a

## Terminal Game Analysis
- `advantage_score = red_utility - blue_utility = 0.667`; red is advantaged because this value is greater than 0.
- `best_response_gain_red = 3.667` versus the Round 2 frozen-blue baseline red utility.
- `best_response_gain_blue = 5.000` from the most recent completed blue optimization round.
- Empirical approximate Nash stability is not claimed: at least one recent best-response gain is positive in this finite search space.

## Iteration Record
- target_side: red
- frozen opponent: blue
- parameter sweep trials: 29
- controlled policy code iterations: 1
- final status: PASS
