# AutoResearch Round 5: red

## Scope
- Scenario: `scenarios/vertical_wave_3v3_001/`
- Policy: `policies/vertical_wave_3v3_rule_v1_r05_red/`
- Target side: `red`; frozen opponent: `blue` from Round 4 best trial `trial_0007`.
- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.
- Sweep: 18 trials from `search_space.yaml` priority_1 budget; code iterations: 10.
- Ranking: feasible hard constraints first, then primary evaluation metric `team_score`/red utility descending, then `avg_episode_length` ascending.

## Best Trial
- Best trial: `trial_0012`
- red_utility: 9.000
- blue_utility: 9.333
- red_utility - blue_utility: -0.333
- hard_constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- primary std across seeds: 2.449
- best_response_gain_red: 4.000
- coupling load: U_R(red,empty_blue)=10.000, U_R(red,true_blue)=9.000, Delta_R=1.000
- decision: FAIL

## Hypotheses And Results
- Baseline hypothesis: Baseline red parameters should establish the Round 5 score against frozen Round 4 blue.
- Winning hypothesis: Changing red_risk_margin=1.0, red_breakout_gain=0.8, red_screen_gain=0.8 should improve red gate progress without violating safety constraints.
- The initial parameter-only sweep failed the red advantage target. Code iterations 1-6 explored defender standoff variants but could not satisfy safety and target together; code iteration 7 added red racer vertical split-lane drive; code iteration 8 added a red gate-frame guard; code iteration 9 disabled split-lane dispatch after gate-frame regressions; code iteration 10 added a small red-only comeback boost when red trails. BluePolicy and frozen blue parameters were not changed.

## Leaderboard Top 3
1. `trial_0012`: feasible=True, red-blue=-0.333, red_score=9.000, collision=0.000, Delta_R=1.0
2. `trial_0002`: feasible=True, red-blue=-1.667, red_score=8.000, collision=0.000, Delta_R=n/a
3. `trial_0014`: feasible=True, red-blue=-1.333, red_score=7.333, collision=0.000, Delta_R=n/a

## Terminal Game Analysis
- `advantage_score = red_utility - blue_utility = -0.333`; red is not advantaged because this value is not greater than 0.
- `best_response_gain_red = 4.000` versus the Round 4 frozen-blue baseline red utility of 5.000.
- `best_response_gain_blue = 0.333` from the most recent completed blue optimization round.
- Empirical approximate Nash stability is not claimed: at least one recent best-response gain is positive in this finite search space.

## Iteration Record
- target_side: red
- frozen opponent: blue
- parameter sweep trials: 18
- controlled policy code iterations: 10
- final status: FAIL

## Validation
- Final experiment package must be validated with `python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r05_red`.
