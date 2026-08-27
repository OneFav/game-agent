# AutoResearch Round 4: blue

## Scope
- Scenario: `scenarios/vertical_wave_3v3_001/`
- Policy: `policies/vertical_wave_3v3_rule_v1_r04_blue/`
- Target side: `blue`; frozen opponent: `red`
- Utility source: `red_utility=avg_red_score`, `blue_utility=avg_blue_score` from evaluator score outputs.
- Sweep: 12 trials, seeds `11,17,23`; priority_2 `blue_defender_mode=escort` was added after the priority_1 intercept plateau.
- Ranking: feasible hard constraints first, then `blue_utility_minus_red_utility` descending, then `avg_episode_length` ascending.

## Best Trial
- Best trial: `trial_0007`
- red_utility: 5.000
- blue_utility: 8.333
- blue_utility - red_utility: 3.333
- hard_constraints: collision_rate=0.000, out_of_bounds_rate=0.000, action_violation_rate=0.000
- primary std across seeds: 1.247
- best_response_gain_blue: 0.333
- coupling load: U_B(blue,empty_red)=14.000, U_B(blue,true_red)=8.333, delta_B=5.667
- decision: PASS

## Hypotheses And Results
- `trial_0007`: Escort low-speed moderate gain tests if less defender perturbation preserves the positive margin with lower variance. Result blue-red=3.333, feasible=True.
- `trial_0009`: Escort lower pressure buffer tests if slightly closer pressure increases blue score while the new frame guard handles safety. Result blue-red=3.333, feasible=True.
- `trial_0004`: Priority-2 escort promotion: use high blue safety and tight lanes while guard prevents defender gate-frame collision. Result blue-red=3.333, feasible=True.
- `trial_0003`: Previous near-best intercept: faster blue racers may recover score if defender gate guard removes the gate-frame failure. Result blue-red=1.667, feasible=True.
- `trial_0010`: Escort faster racers with short radius tests blue scoring speed while avoiding long-range defender drift. Result blue-red=1.667, feasible=True.
- `trial_0011`: Escort lower risk margin tests if relaxing braking improves throughput after guard without collisions. Result blue-red=1.667, feasible=True.
- `trial_0005`: Escort with faster racers and long pressure radius tests whether extra speed improves all-seed blue margin after guard. Result blue-red=1.000, feasible=True.
- `trial_0002`: Previous best feasible intercept: low speed, high margin, tight lane should remain safe and define the intercept plateau. Result blue-red=0.667, feasible=True.
- `trial_0006`: Escort high-speed moderate pressure tests whether lower pressure reduces seed-17 red counterprogress. Result blue-red=0.333, feasible=True.
- `trial_0008`: Escort wider lane tests whether racer separation improves seed-17 stability without sacrificing seed-11 scoring. Result blue-red=-7.667, feasible=True.
- `trial_0012`: Escort lower gain at speed 7.0 tests a conservative fast-racer alternative for tie-breaking. Result blue-red=-0.333, feasible=False.
- `trial_0001`: Baseline Round-4 intercept config: verify code iteration does not regress the original safe baseline. Result blue-red=-4.667, feasible=False.

## Leaderboard Top 3
1. `trial_0007`: feasible=true, blue-red=3.333, blue_score=8.333, collision=0.000, delta_B=5.666667
2. `trial_0009`: feasible=true, blue-red=3.333, blue_score=8.333, collision=0.000, delta_B=n/a
3. `trial_0004`: feasible=true, blue-red=3.333, blue_score=9.667, collision=0.000, delta_B=n/a

## Iteration Record
- target_side: blue
- frozen opponent: red
- parameter sweep trials: 12 final trials with 3 eval seeds each
- controlled policy code iterations: 4 total (3 previous + 1 continued iteration)
- iteration 4 hypothesis: blue escort mode already produced positive margins but collided with gate frames; adding a blue-only defender gate-frame guard should preserve score while satisfying hard constraints.
- final status: PASS
- failure reason: n/a

## Terminal Game Analysis
- `advantage_score = red_utility - blue_utility = -3.333`; blue is advantaged because this value is less than 0.
- `best_response_gain_blue = 0.333` versus the Round 3 frozen-red baseline blue utility of 8.000.
- `best_response_gain_red = 3.667` from the most recent completed red optimization round.
- Empirical approximate Nash stability is not claimed: the recent red best-response gain remains positive, so the current pair is not approximately stable under the finite-search criterion.

## Verification Notes
- Policy hook and package tests passed after controlled policy code iteration 4 before the final sweep.
- Final experiment package was validated with `python src/hooks/post_experiment_run.py --exp experiments/vertical_wave_3v3_exp_001_r04_blue`.
