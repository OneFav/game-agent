# AutoResearch Round 2: blue

## Scope
- Scenario: `scenarios/vertical_wave_3v3_001/`
- Policy: `policies/vertical_wave_3v3_rule_v1_r02_blue/`
- Target side: `blue`; frozen opponent: `red`
- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.
- Sweep: 12 priority_1 trials, seeds `11,17,23`.
- Ranking: feasible promotion gates first, then `blue_utility_minus_red_utility` descending, then `avg_episode_length` ascending.

## Best Trial
- Best trial: `trial_0011`
- red_utility: 5.000
- blue_utility: 9.000
- blue_utility - red_utility: 4.000
- hard_constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- primary std across seeds: 2.160
- best_response_gain_blue: 5.000
- coupling load: U_B(blue,empty_red)=11.667, U_B(blue,true_red)=9.000, delta_B=2.667
- decision: PASS

## Hypotheses And Results
Each trial changed only `blue_desired_speed`, `blue_risk_margin`, and `blue_lane_spacing`. Red parameters and shared parameters stayed frozen from `default_config.yaml`/`do_not_tune`. The winning hypothesis was that medium blue speed with low risk margin and default lane spacing keeps the blue racers safe while increasing gate throughput against frozen red.

## Leaderboard Top 3
1. `trial_0011`: feasible=True, blue-red=4.000, collision=0.000, delta_B=2.666666666666666
2. `trial_0005`: feasible=False, blue-red=4.333, collision=0.333, delta_B=n/a
3. `trial_0001`: feasible=False, blue-red=4.000, collision=0.000, delta_B=-0.3333333333333339

## Terminal Game Analysis
- `advantage_score = red_utility - blue_utility = -4.000`; by the Round 2 target criterion, blue is advantaged because `blue_utility - red_utility = 4.000 > 0`.
- `best_response_gain_blue = 5.000` versus the Round 1 initial blue utility baseline.
- `best_response_gain_red = n/a` for rounds completed up to Round 2 because no red best-response round has been executed in this requested current round window.
- Empirical approximate Nash stability is not claimed from Round 2 alone.

## Iteration Record
- target_side: blue
- frozen opponent: red
- parameter sweep trials: 12
- controlled policy code iterations: 0
- final status: PASS
